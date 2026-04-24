from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from datetime import datetime, timezone
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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
    provider=settings.stt_provider,
    compute_type=settings.stt_compute_type,
    whisper_cpp_bin=settings.stt_cpp_bin,
    whisper_cpp_model_path=settings.stt_cpp_model_path,
    whisper_cpp_quantization=settings.stt_cpp_quant,
    whisper_cpp_threads=settings.stt_cpp_threads,
    whisper_cpp_language=settings.stt_cpp_language,
    whisper_cpp_fallback_to_faster=settings.stt_cpp_fallback_to_faster,
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
    keep_alive=settings.llm_keep_alive,
)
uart_gateway: UartGateway | None = None
llm_keepalive_task: asyncio.Task | None = None
llm_warmup_state: dict[str, Any] = {
    "enabled": settings.llm_warmup_on_startup,
    "ok": None,
    "message": "warmup not started",
    "last_keepalive_at": None,
}
service_started_at = datetime.now(timezone.utc).isoformat()


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_TRANSPORT_MODES = {"wifi", "bluetooth", "wired"}
SERIAL_TRANSPORT_MODES = {"bluetooth", "wired"}
SUPPORTED_AUDIO_CODECS = {"ulaw8k", "pcm16", "pcm16le"}
transport_config_lock = asyncio.Lock()


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _to_int(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _serial_defaults(port: str) -> dict[str, Any]:
    return {
        "port": port,
        "baudrate": settings.uart_baudrate,
        "timeout_ms": settings.uart_timeout_ms,
        "read_size": settings.uart_read_size,
        "frame_payload_bytes": settings.uart_frame_payload_bytes,
        "audio_codec": settings.uart_audio_codec,
        "device_sample_rate": settings.uart_device_sample_rate,
    }


def _default_transport_config() -> dict[str, Any]:
    default_mode = settings.transport_default_mode.strip().lower() or "wifi"
    if default_mode not in SUPPORTED_TRANSPORT_MODES:
        default_mode = "wifi"

    if settings.uart_enabled and default_mode == "wifi":
        default_mode = "wired"

    enabled = True if default_mode == "wifi" else settings.uart_enabled

    return {
        "mode": default_mode,
        "enabled": enabled,
        "wifi": {"ws_path": settings.ws_path},
        "bluetooth": _serial_defaults(settings.bluetooth_default_port),
        "wired": _serial_defaults(settings.uart_port),
    }


def _normalize_serial_config(raw: Any, fallback_port: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    codec_raw = str(raw.get("audio_codec", settings.uart_audio_codec)).strip().lower()
    codec = codec_raw if codec_raw in SUPPORTED_AUDIO_CODECS else settings.uart_audio_codec

    return {
        "port": str(raw.get("port", fallback_port)).strip() or fallback_port,
        "baudrate": _to_int(raw.get("baudrate", settings.uart_baudrate), settings.uart_baudrate, 1200),
        "timeout_ms": _to_int(raw.get("timeout_ms", settings.uart_timeout_ms), settings.uart_timeout_ms, 1),
        "read_size": _to_int(raw.get("read_size", settings.uart_read_size), settings.uart_read_size, 64),
        "frame_payload_bytes": _to_int(
            raw.get("frame_payload_bytes", settings.uart_frame_payload_bytes),
            settings.uart_frame_payload_bytes,
            64,
        ),
        "audio_codec": codec,
        "device_sample_rate": _to_int(
            raw.get("device_sample_rate", settings.uart_device_sample_rate),
            settings.uart_device_sample_rate,
            4000,
        ),
    }


def _normalize_transport_config(raw: Any) -> dict[str, Any]:
    defaults = _default_transport_config()
    if not isinstance(raw, dict):
        raw = {}

    mode = str(raw.get("mode", defaults["mode"]))
    mode = mode.strip().lower() or defaults["mode"]
    if mode not in SUPPORTED_TRANSPORT_MODES:
        mode = defaults["mode"]

    enabled = _to_bool(raw.get("enabled", defaults["enabled"]), defaults["enabled"])
    wifi_raw = raw.get("wifi", defaults["wifi"])
    wifi_ws_path = settings.ws_path
    if isinstance(wifi_raw, dict):
        wifi_ws_path = str(wifi_raw.get("ws_path", settings.ws_path)).strip() or settings.ws_path

    return {
        "mode": mode,
        "enabled": enabled,
        "wifi": {"ws_path": wifi_ws_path},
        "bluetooth": _normalize_serial_config(
            raw.get("bluetooth", defaults["bluetooth"]), settings.bluetooth_default_port
        ),
        "wired": _normalize_serial_config(raw.get("wired", defaults["wired"]), settings.uart_port),
    }


def _deep_merge_dict(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(current, value)
        else:
            merged[key] = value
    return merged


def _load_transport_config() -> dict[str, Any]:
    path = Path(settings.transport_config_path)
    if not path.exists():
        return _default_transport_config()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read transport config, fallback to defaults: %s", exc)
        return _default_transport_config()

    return _normalize_transport_config(payload)


def _save_transport_config(config: dict[str, Any]) -> None:
    path = Path(settings.transport_config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


transport_config = _load_transport_config()


def _serial_runtime_settings(serial_cfg: dict[str, Any]):
    return replace(
        settings,
        uart_enabled=True,
        uart_port=serial_cfg["port"],
        uart_baudrate=serial_cfg["baudrate"],
        uart_timeout_ms=serial_cfg["timeout_ms"],
        uart_read_size=serial_cfg["read_size"],
        uart_frame_payload_bytes=serial_cfg["frame_payload_bytes"],
        uart_audio_codec=serial_cfg["audio_codec"],
        uart_device_sample_rate=serial_cfg["device_sample_rate"],
    )


async def _stop_uart_gateway() -> None:
    global uart_gateway
    if uart_gateway is not None:
        await uart_gateway.stop()
        uart_gateway = None


async def _apply_transport_config() -> None:
    global uart_gateway

    mode = transport_config["mode"]
    enabled = transport_config["enabled"]

    if mode == "wifi" or not enabled:
        await _stop_uart_gateway()
        return

    if mode not in SERIAL_TRANSPORT_MODES:
        await _stop_uart_gateway()
        return

    serial_cfg = transport_config[mode]
    runtime_settings = _serial_runtime_settings(serial_cfg)

    await _stop_uart_gateway()
    gateway = UartGateway(
        settings=runtime_settings,
        stt_service=stt_service,
        rag_service=rag_service,
        llm_service=llm_service,
        ingest_threshold_bytes=INGEST_THRESHOLD_BYTES,
    )
    await gateway.start()
    uart_gateway = gateway


def _build_transport_status() -> dict[str, Any]:
    mode = transport_config["mode"]
    enabled = transport_config["enabled"]
    gateway_status = uart_gateway.snapshot() if uart_gateway is not None else None
    return {
        "mode": mode,
        "enabled": enabled,
        "serial_mode": mode in SERIAL_TRANSPORT_MODES,
        "gateway_running": bool(gateway_status and gateway_status.get("running")),
        "gateway_connected": bool(gateway_status and gateway_status.get("connected")),
    }


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


def _load_prewarm_status(status_path: str, component: str) -> dict[str, Any]:
    path = Path(status_path)
    if not path.exists():
        return {
            "component": component,
            "available": False,
            "ok": None,
            "message": "status file not found",
            "path": status_path,
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "component": component,
            "available": False,
            "ok": False,
            "message": f"invalid status file: {exc}",
            "path": status_path,
        }

    payload.setdefault("component", component)
    payload["available"] = True
    payload["path"] = status_path
    return payload


def _build_prewarm_status() -> dict[str, Any]:
    return {
        "stt": _load_prewarm_status(settings.stt_prewarm_status_file, "stt"),
        "piper": _load_prewarm_status(settings.piper_prewarm_status_file, "piper"),
    }


def _build_uart_status() -> dict[str, Any]:
    mode = transport_config.get("mode", "wifi")
    enabled = _to_bool(transport_config.get("enabled", False), False)
    serial_cfg = transport_config.get(mode, {}) if mode in SERIAL_TRANSPORT_MODES else {}

    if mode not in SERIAL_TRANSPORT_MODES or not enabled:
        return {
            "enabled": False,
            "running": False,
            "connected": False,
            "port": serial_cfg.get("port", settings.uart_port),
            "baudrate": serial_cfg.get("baudrate", settings.uart_baudrate),
            "audio_codec": serial_cfg.get("audio_codec", settings.uart_audio_codec),
        }

    if uart_gateway is None:
        return {
            "enabled": True,
            "running": False,
            "connected": False,
            "port": serial_cfg.get("port", settings.uart_port),
            "baudrate": serial_cfg.get("baudrate", settings.uart_baudrate),
            "audio_codec": serial_cfg.get("audio_codec", settings.uart_audio_codec),
            "last_error": "uart gateway not initialized",
        }

    return uart_gateway.snapshot()


def _build_llm_status() -> dict[str, Any]:
    keepalive_running = llm_keepalive_task is not None and not llm_keepalive_task.done()
    return {
        "model": settings.llm_model,
        "host": settings.ollama_host,
        "keep_alive": settings.llm_keep_alive,
        "warmup": {
            "enabled": llm_warmup_state["enabled"],
            "ok": llm_warmup_state["ok"],
            "message": llm_warmup_state["message"],
        },
        "keepalive": {
            "enabled": settings.llm_keepalive_enabled,
            "interval_seconds": settings.llm_keepalive_interval_seconds,
            "running": keepalive_running,
            "last_keepalive_at": llm_warmup_state["last_keepalive_at"],
            "prompt": settings.llm_keepalive_prompt,
        },
    }


async def _llm_keepalive_loop() -> None:
    interval = max(1, settings.llm_keepalive_interval_seconds)
    while True:
        await asyncio.sleep(interval)
        ok, message = await llm_service.warmup(
            prompt=settings.llm_keepalive_prompt,
            timeout_seconds=settings.llm_warmup_timeout_seconds,
            retries=0,
            retry_delay_seconds=0.0,
        )
        llm_warmup_state["last_keepalive_at"] = datetime.now(timezone.utc).isoformat()
        llm_warmup_state["message"] = f"keepalive {'ok' if ok else 'failed'}: {message}"
        if not ok:
            logger.warning("LLM keepalive failed: %s", message)


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
    global llm_keepalive_task, transport_config

    tts_status = _build_tts_status()
    stt_status = stt_service.status()
    logger.info(
        "Startup summary | llm_model=%s stt_provider=%s stt_backend=%s stt_model=%s rag_mode=%s",
        settings.llm_model,
        settings.stt_provider,
        stt_status["active_backend"],
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
    logger.info(
        "Startup summary | prewarm_status_files stt=%s piper=%s",
        settings.stt_prewarm_status_file,
        settings.piper_prewarm_status_file,
    )
    llm_warmup_state["enabled"] = settings.llm_warmup_on_startup
    if settings.llm_warmup_on_startup:
        ok, message = await llm_service.warmup(
            prompt=settings.llm_warmup_prompt,
            timeout_seconds=settings.llm_warmup_timeout_seconds,
            retries=settings.llm_warmup_retries,
            retry_delay_seconds=settings.llm_warmup_retry_delay_seconds,
        )
        llm_warmup_state["ok"] = ok
        llm_warmup_state["message"] = message
        logger.info("LLM warmup result | ok=%s message=%s", ok, message)
    else:
        llm_warmup_state["ok"] = None
        llm_warmup_state["message"] = "warmup disabled by config"

    if settings.llm_keepalive_enabled:
        llm_keepalive_task = asyncio.create_task(_llm_keepalive_loop(), name="llm_keepalive_loop")
        logger.info(
            "LLM keepalive started | interval_seconds=%s keep_alive=%s",
            settings.llm_keepalive_interval_seconds,
            settings.llm_keep_alive,
        )
    else:
        llm_keepalive_task = None
        logger.info("LLM keepalive disabled by config")

    async with transport_config_lock:
        transport_config = _normalize_transport_config(transport_config)
        _save_transport_config(transport_config)
        await _apply_transport_config()

    logger.info(
        "Startup summary | transport_mode=%s enabled=%s",
        transport_config["mode"],
        transport_config["enabled"],
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global llm_keepalive_task
    if llm_keepalive_task is not None:
        llm_keepalive_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await llm_keepalive_task
        llm_keepalive_task = None
    await _stop_uart_gateway()


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "edge-voice-rag",
        "status": "running",
        "ws": settings.ws_path,
        "startup_at": service_started_at,
        "transport": _build_transport_status(),
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    tts_status = _build_tts_status()
    uart_status = _build_uart_status()
    prewarm_status = _build_prewarm_status()
    stt_status = stt_service.status()
    status = "ok" if tts_status["tts_mode"] != "unavailable" else "degraded"
    return {
        "status": status,
        "startup_at": service_started_at,
        "stt_backend": stt_service.backend,
        "stt_provider": settings.stt_provider,
        "stt_model": settings.stt_model,
        "stt": stt_status,
        "rag_mode": rag_service.mode,
        "llm_model": settings.llm_model,
        "llm": _build_llm_status(),
        "transport": _build_transport_status(),
        "uart": uart_status,
        "prewarm": prewarm_status,
        **tts_status,
    }


@app.get("/api/dashboard/transport")
async def get_transport_dashboard() -> dict[str, Any]:
    async with transport_config_lock:
        return {
            "config": transport_config,
            "status": _build_transport_status(),
            "ws_path": settings.ws_path,
        }


@app.put("/api/dashboard/transport")
async def update_transport_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    global transport_config

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid transport payload")

    async with transport_config_lock:
        merged = _deep_merge_dict(transport_config, payload)
        next_config = _normalize_transport_config(merged)
        if next_config == transport_config:
            return {
                "config": transport_config,
                "status": _build_transport_status(),
                "ws_path": settings.ws_path,
            }

        transport_config = next_config
        _save_transport_config(transport_config)
        await _apply_transport_config()
        return {
            "config": transport_config,
            "status": _build_transport_status(),
            "ws_path": settings.ws_path,
        }


@app.websocket(settings.ws_path)
async def audio_websocket_endpoint(websocket: WebSocket) -> None:
    async with transport_config_lock:
        wifi_enabled = transport_config.get("mode") == "wifi" and _to_bool(transport_config.get("enabled", False), False)

    if not wifi_enabled:
        await websocket.accept()
        await websocket.send_text(json.dumps({"event": "error", "message": "wifi transport is disabled"}))
        await websocket.close(code=1008)
        return

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
                "transport_mode": "wifi",
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
