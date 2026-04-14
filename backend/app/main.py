from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.llm_inference import OllamaLLMService
from app.services.rag_retrieval import RAGService
from app.services.stt_engine import STTService
from app.services.tts_pipeline import PiperTTSService
from app.services.uart_gateway import UartGateway

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

INGEST_THRESHOLD_BYTES = int(settings.sample_rate * 2 * settings.audio_chunk_seconds)

stt_service = STTService(
    sample_rate=settings.sample_rate,
    min_silence_ms=settings.vad_min_silence_ms,
    threshold=settings.vad_threshold,
    model_name=settings.stt_model,
)
rag_service = RAGService(
    knowledge_dir=settings.knowledge_dir,
    lancedb_dir=settings.lancedb_dir,
    table_name=settings.lancedb_table,
    vector_dim=settings.vector_dim,
)
llm_service = OllamaLLMService(
    host=settings.ollama_host,
    model=settings.llm_model,
    num_ctx=settings.llm_num_ctx,
    temperature=settings.llm_temperature,
    top_k=settings.llm_top_k,
)
uart_gateway: UartGateway | None = None


@dataclass
class SessionState:
    websocket: WebSocket
    tts_service: PiperTTSService

    inbound_audio_buffer: bytearray = field(default_factory=bytearray)
    stt_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=8))
    text_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=8))
    sentence_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=16))
    outbound_audio_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=32))

    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task] = field(default_factory=list)


app = FastAPI(title="Edge Voice RAG Gateway", version="0.1.0")


def _build_tts_status() -> dict[str, str | bool]:
    piper_bin_path = shutil.which(settings.piper_bin) or ""
    piper_bin_found = bool(piper_bin_path)
    piper_model_exists = Path(settings.piper_model).exists()

    if piper_bin_found and piper_model_exists:
        tts_mode = "real"
    elif settings.piper_use_mock_on_missing:
        tts_mode = "mock"
    else:
        tts_mode = "unavailable"

    return {
        "piper_bin_found": piper_bin_found,
        "piper_bin_path": piper_bin_path or "missing",
        "piper_model": settings.piper_model,
        "piper_model_exists": piper_model_exists,
        "piper_mock_allowed": settings.piper_use_mock_on_missing,
        "tts_mode": tts_mode,
    }


def _build_uart_status() -> dict[str, Any]:
    if not settings.uart_enabled:
        return {
            "enabled": False,
            "running": False,
            "connected": False,
            "port": settings.uart_port,
            "baudrate": settings.uart_baudrate,
            "audio_codec": settings.uart_audio_codec,
        }

    if uart_gateway is None:
        return {
            "enabled": True,
            "running": False,
            "connected": False,
            "port": settings.uart_port,
            "baudrate": settings.uart_baudrate,
            "audio_codec": settings.uart_audio_codec,
            "last_error": "uart gateway not initialized",
        }

    return uart_gateway.snapshot()


def _clear_queue(queue_obj: asyncio.Queue) -> None:
    while True:
        try:
            queue_obj.get_nowait()
        except asyncio.QueueEmpty:
            break


async def _trigger_interrupt(state: SessionState) -> None:
    state.interrupt_event.set()
    state.inbound_audio_buffer.clear()
    _clear_queue(state.stt_queue)
    _clear_queue(state.text_queue)
    _clear_queue(state.sentence_queue)
    _clear_queue(state.outbound_audio_queue)
    await asyncio.to_thread(state.tts_service.clear_audio_queue)


async def _stt_worker(state: SessionState) -> None:
    while not state.stop_event.is_set():
        try:
            audio_payload = await asyncio.wait_for(state.stt_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue

        if state.interrupt_event.is_set():
            continue

        text = await asyncio.to_thread(stt_service.transcribe, audio_payload)
        if text:
            await state.text_queue.put(text)


async def _llm_worker(state: SessionState) -> None:
    while not state.stop_event.is_set():
        try:
            user_text = await asyncio.wait_for(state.text_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue

        if state.interrupt_event.is_set():
            continue

        contexts = await asyncio.to_thread(rag_service.retrieve_context, user_text, settings.rag_top_k)
        prompt = rag_service.build_prompt(user_text, contexts)

        async for sentence in llm_service.stream_sentences(prompt, state.interrupt_event):
            if state.stop_event.is_set() or state.interrupt_event.is_set():
                break
            await state.sentence_queue.put(sentence)


async def _tts_writer_worker(state: SessionState) -> None:
    while not state.stop_event.is_set():
        try:
            sentence = await asyncio.wait_for(state.sentence_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue

        if state.interrupt_event.is_set():
            continue

        await asyncio.to_thread(state.tts_service.enqueue_sentence, sentence)


async def _tts_drain_worker(state: SessionState) -> None:
    while not state.stop_event.is_set():
        if state.interrupt_event.is_set():
            await asyncio.to_thread(state.tts_service.clear_audio_queue)
            await asyncio.sleep(0.05)
            continue

        chunk = await asyncio.to_thread(state.tts_service.read_audio_chunk, 0.1)
        if not chunk:
            continue

        if state.outbound_audio_queue.full():
            try:
                state.outbound_audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        await state.outbound_audio_queue.put(chunk)


async def _sender_worker(state: SessionState) -> None:
    while not state.stop_event.is_set():
        try:
            chunk = await asyncio.wait_for(state.outbound_audio_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue

        if state.interrupt_event.is_set():
            continue

        await state.websocket.send_bytes(chunk)


async def _shutdown_session(state: SessionState) -> None:
    state.stop_event.set()

    for task in state.tasks:
        task.cancel()

    if state.tasks:
        with contextlib.suppress(Exception):
            await asyncio.gather(*state.tasks, return_exceptions=True)

    await asyncio.to_thread(state.tts_service.shutdown)


@app.on_event("startup")
async def on_startup() -> None:
    global uart_gateway

    tts_status = _build_tts_status()
    logger.info(
        "Startup summary | llm_model=%s stt_model=%s rag_mode=%s",
        settings.llm_model,
        settings.stt_model,
        rag_service.mode,
    )
    logger.info(
        "Startup summary | tts_mode=%s piper_bin=%s piper_model=%s model_exists=%s mock_allowed=%s",
        tts_status["tts_mode"],
        tts_status["piper_bin_path"],
        tts_status["piper_model"],
        tts_status["piper_model_exists"],
        tts_status["piper_mock_allowed"],
    )

    if settings.uart_enabled:
        uart_gateway = UartGateway(
            settings=settings,
            stt_service=stt_service,
            rag_service=rag_service,
            llm_service=llm_service,
            ingest_threshold_bytes=INGEST_THRESHOLD_BYTES,
        )
        await uart_gateway.start()
        logger.info(
            "Startup summary | uart_enabled=%s port=%s baudrate=%s codec=%s",
            settings.uart_enabled,
            settings.uart_port,
            settings.uart_baudrate,
            settings.uart_audio_codec,
        )
    else:
        logger.info("Startup summary | uart_enabled=%s", settings.uart_enabled)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global uart_gateway
    if uart_gateway is not None:
        await uart_gateway.stop()
        uart_gateway = None


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "edge-voice-rag",
        "status": "running",
        "ws": settings.ws_path,
        "uart_enabled": settings.uart_enabled,
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    tts_status = _build_tts_status()
    uart_status = _build_uart_status()
    status = "ok" if tts_status["tts_mode"] != "unavailable" else "degraded"
    return {
        "status": status,
        "stt_backend": stt_service.backend,
        "stt_model": settings.stt_model,
        "rag_mode": rag_service.mode,
        "llm_model": settings.llm_model,
        "uart": uart_status,
        **tts_status,
    }


@app.websocket(settings.ws_path)
async def audio_websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    tts_service = PiperTTSService(
        piper_bin=settings.piper_bin,
        model_path=settings.piper_model,
        sample_rate=settings.sample_rate,
        chunk_size=settings.piper_chunk_size,
        allow_mock_on_missing=settings.piper_use_mock_on_missing,
    )
    await asyncio.to_thread(tts_service.start)

    state = SessionState(websocket=websocket, tts_service=tts_service)
    state.tasks = [
        asyncio.create_task(_stt_worker(state)),
        asyncio.create_task(_llm_worker(state)),
        asyncio.create_task(_tts_writer_worker(state)),
        asyncio.create_task(_tts_drain_worker(state)),
        asyncio.create_task(_sender_worker(state)),
    ]

    await websocket.send_text(
        json.dumps(
            {
                "event": "ready",
                "sample_rate": settings.sample_rate,
                "threshold_bytes": INGEST_THRESHOLD_BYTES,
            }
        )
    )

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            audio_chunk = message.get("bytes")
            if audio_chunk is not None:
                if state.interrupt_event.is_set():
                    state.interrupt_event.clear()

                state.inbound_audio_buffer.extend(audio_chunk)
                if len(state.inbound_audio_buffer) >= INGEST_THRESHOLD_BYTES:
                    payload = bytes(state.inbound_audio_buffer)
                    state.inbound_audio_buffer.clear()

                    if state.stt_queue.full():
                        try:
                            state.stt_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await state.stt_queue.put(payload)
                continue

            text_payload = message.get("text")
            if text_payload is None:
                continue

            try:
                signal = json.loads(text_payload)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON control frame")
                continue

            action = signal.get("action")
            if action == "interrupt":
                await _trigger_interrupt(state)
            elif action in {"speech_start", "resume"}:
                state.interrupt_event.clear()
            elif action == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    finally:
        await _shutdown_session(state)
