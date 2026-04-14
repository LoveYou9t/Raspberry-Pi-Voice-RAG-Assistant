from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.services.audio_codec import device_audio_to_stt_audio, tts_audio_to_device_audio
from app.services.llm_inference import OllamaLLMService
from app.services.rag_retrieval import RAGService
from app.services.serial_framing import FrameParser, FrameType, encode_frame
from app.services.serial_link import SerialTransport, SerialTransportError
from app.services.stt_engine import STTService
from app.services.tts_pipeline import PiperTTSService

logger = logging.getLogger(__name__)


@dataclass
class UartSessionState:
    transport: SerialTransport
    frame_parser: FrameParser
    tts_service: PiperTTSService

    frame_payload_bytes: int
    baudrate: int
    audio_codec: str
    device_sample_rate: int
    stt_sample_rate: int

    inbound_audio_buffer: bytearray = field(default_factory=bytearray)
    stt_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=8))
    text_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=8))
    sentence_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=16))
    outbound_audio_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=32))

    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task] = field(default_factory=list)

    tx_seq: int = 0
    rx_frames: int = 0
    tx_frames: int = 0


def _clear_queue(queue_obj: asyncio.Queue) -> None:
    while True:
        try:
            queue_obj.get_nowait()
        except asyncio.QueueEmpty:
            break


class UartGateway:
    def __init__(
        self,
        settings: Settings,
        stt_service: STTService,
        rag_service: RAGService,
        llm_service: OllamaLLMService,
        ingest_threshold_bytes: int,
    ) -> None:
        self.settings = settings
        self.stt_service = stt_service
        self.rag_service = rag_service
        self.llm_service = llm_service
        self.ingest_threshold_bytes = ingest_threshold_bytes

        self._state: UartSessionState | None = None
        self._status: dict[str, Any] = {
            "enabled": settings.uart_enabled,
            "running": False,
            "connected": False,
            "port": settings.uart_port,
            "baudrate": settings.uart_baudrate,
            "audio_codec": settings.uart_audio_codec,
            "device_sample_rate": settings.uart_device_sample_rate,
            "rx_frames": 0,
            "tx_frames": 0,
            "crc_errors": 0,
            "dropped_bytes": 0,
            "last_error": "",
        }

    def snapshot(self) -> dict[str, Any]:
        snapshot = dict(self._status)
        state = self._state
        if state is None:
            return snapshot

        snapshot.update(
            {
                "running": not state.stop_event.is_set(),
                "connected": state.transport.is_open,
                "rx_frames": state.rx_frames,
                "tx_frames": state.tx_frames,
                "crc_errors": state.frame_parser.crc_errors,
                "dropped_bytes": state.frame_parser.dropped_bytes,
            }
        )
        return snapshot

    async def start(self) -> None:
        if not self.settings.uart_enabled:
            logger.info("UART gateway disabled by configuration.")
            return

        if self._state is not None:
            logger.info("UART gateway already running.")
            return

        transport = SerialTransport(
            port=self.settings.uart_port,
            baudrate=self.settings.uart_baudrate,
            timeout_seconds=max(0.01, self.settings.uart_timeout_ms / 1000.0),
            write_timeout_seconds=0.5,
            read_size=self.settings.uart_read_size,
        )

        try:
            await asyncio.to_thread(transport.open)
        except SerialTransportError as exc:
            self._status["last_error"] = str(exc)
            logger.error("UART gateway startup failed: %s", exc)
            return

        tts_service = PiperTTSService(
            piper_bin=self.settings.piper_bin,
            model_path=self.settings.piper_model,
            sample_rate=self.settings.sample_rate,
            chunk_size=self.settings.piper_chunk_size,
            allow_mock_on_missing=self.settings.piper_use_mock_on_missing,
        )
        await asyncio.to_thread(tts_service.start)

        state = UartSessionState(
            transport=transport,
            frame_parser=FrameParser(max_payload_size=max(64, self.settings.uart_frame_payload_bytes * 2)),
            tts_service=tts_service,
            frame_payload_bytes=max(64, self.settings.uart_frame_payload_bytes),
            baudrate=self.settings.uart_baudrate,
            audio_codec=self.settings.uart_audio_codec,
            device_sample_rate=self.settings.uart_device_sample_rate,
            stt_sample_rate=self.settings.sample_rate,
        )

        state.tasks = [
            asyncio.create_task(self._serial_reader_worker(state)),
            asyncio.create_task(self._stt_worker(state)),
            asyncio.create_task(self._llm_worker(state)),
            asyncio.create_task(self._tts_writer_worker(state)),
            asyncio.create_task(self._tts_drain_worker(state)),
            asyncio.create_task(self._serial_sender_worker(state)),
        ]
        self._state = state
        self._status["running"] = True
        self._status["connected"] = True
        self._status["last_error"] = ""

        await self._send_control(
            state,
            event="ready",
            payload={
                "stt_sample_rate": self.settings.sample_rate,
                "device_sample_rate": self.settings.uart_device_sample_rate,
                "audio_codec": self.settings.uart_audio_codec,
                "threshold_bytes": self.ingest_threshold_bytes,
            },
        )

        logger.info(
            "UART gateway started | port=%s baudrate=%s codec=%s",
            self.settings.uart_port,
            self.settings.uart_baudrate,
            self.settings.uart_audio_codec,
        )

    async def stop(self) -> None:
        state = self._state
        if state is None:
            self._status["running"] = False
            self._status["connected"] = False
            return

        state.stop_event.set()
        for task in state.tasks:
            task.cancel()

        with contextlib.suppress(Exception):
            await asyncio.gather(*state.tasks, return_exceptions=True)

        await asyncio.to_thread(state.tts_service.shutdown)
        await asyncio.to_thread(state.transport.close)

        self._status.update(
            {
                "running": False,
                "connected": False,
                "rx_frames": state.rx_frames,
                "tx_frames": state.tx_frames,
                "crc_errors": state.frame_parser.crc_errors,
                "dropped_bytes": state.frame_parser.dropped_bytes,
            }
        )
        self._state = None

    async def _send_control(self, state: UartSessionState, event: str, payload: dict[str, Any] | None = None) -> None:
        body = {"event": event}
        if payload:
            body.update(payload)

        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        await self._send_frame(state, frame_type=FrameType.CONTROL, payload=encoded)

    async def _send_frame(
        self,
        state: UartSessionState,
        frame_type: int,
        payload: bytes,
        flags: int = 0,
    ) -> None:
        frame = encode_frame(
            frame_type=frame_type,
            seq=state.tx_seq,
            payload=payload,
            flags=flags,
        )
        state.tx_seq = (state.tx_seq + 1) & 0xFFFF

        try:
            await asyncio.to_thread(state.transport.write, frame)
            state.tx_frames += 1
        except SerialTransportError as exc:
            self._status["last_error"] = str(exc)
            logger.error("UART write failed: %s", exc)
            state.stop_event.set()
            return

        # UART line pacing at 8N1: 10 bits per byte.
        bits_per_byte = 10.0
        await asyncio.sleep((len(frame) * bits_per_byte) / max(1, state.baudrate))

    async def _flush_inbound_buffer(self, state: UartSessionState, force: bool) -> None:
        if not state.inbound_audio_buffer:
            return
        if not force and len(state.inbound_audio_buffer) < self.ingest_threshold_bytes:
            return

        payload = bytes(state.inbound_audio_buffer)
        state.inbound_audio_buffer.clear()

        if state.stt_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                state.stt_queue.get_nowait()
        await state.stt_queue.put(payload)

    async def _trigger_interrupt(self, state: UartSessionState) -> None:
        state.interrupt_event.set()
        state.inbound_audio_buffer.clear()
        _clear_queue(state.stt_queue)
        _clear_queue(state.text_queue)
        _clear_queue(state.sentence_queue)
        _clear_queue(state.outbound_audio_queue)
        await asyncio.to_thread(state.tts_service.clear_audio_queue)

    async def _handle_control(self, state: UartSessionState, payload: bytes) -> None:
        try:
            signal = json.loads(payload.decode("utf-8"))
        except Exception:
            logger.warning("UART control frame is not valid JSON")
            return

        action = signal.get("action")
        if action == "interrupt":
            await self._trigger_interrupt(state)
            return
        if action in {"speech_start", "resume"}:
            state.interrupt_event.clear()
            return
        if action == "speech_end":
            await self._flush_inbound_buffer(state, force=True)
            return
        if action == "ping":
            await self._send_control(state, event="pong")

    async def _serial_reader_worker(self, state: UartSessionState) -> None:
        while not state.stop_event.is_set():
            try:
                chunk = await asyncio.to_thread(state.transport.read, self.settings.uart_read_size)
            except SerialTransportError as exc:
                self._status["last_error"] = str(exc)
                logger.error("UART read failed: %s", exc)
                state.stop_event.set()
                break

            if not chunk:
                await asyncio.sleep(0.01)
                continue

            frames = state.frame_parser.feed(chunk)
            for frame in frames:
                state.rx_frames += 1
                frame_type = frame.frame_type

                if frame_type == FrameType.AUDIO_UP:
                    if state.interrupt_event.is_set():
                        state.interrupt_event.clear()

                    try:
                        pcm_payload = device_audio_to_stt_audio(
                            frame.payload,
                            codec=state.audio_codec,
                            device_sample_rate=state.device_sample_rate,
                            stt_sample_rate=state.stt_sample_rate,
                        )
                    except ValueError as exc:
                        self._status["last_error"] = str(exc)
                        logger.error("Unsupported audio codec: %s", exc)
                        continue

                    state.inbound_audio_buffer.extend(pcm_payload)
                    await self._flush_inbound_buffer(state, force=False)
                    continue

                if frame_type == FrameType.CONTROL:
                    await self._handle_control(state, frame.payload)
                    continue

                if frame_type == FrameType.HEARTBEAT:
                    await self._send_frame(state, frame_type=FrameType.ACK, payload=b"")

    async def _stt_worker(self, state: UartSessionState) -> None:
        while not state.stop_event.is_set():
            try:
                audio_payload = await asyncio.wait_for(state.stt_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            if state.interrupt_event.is_set():
                continue

            text = await asyncio.to_thread(self.stt_service.transcribe, audio_payload)
            if text:
                await state.text_queue.put(text)

    async def _llm_worker(self, state: UartSessionState) -> None:
        while not state.stop_event.is_set():
            try:
                user_text = await asyncio.wait_for(state.text_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            if state.interrupt_event.is_set():
                continue

            contexts = await asyncio.to_thread(self.rag_service.retrieve_context, user_text, self.settings.rag_top_k)
            prompt = self.rag_service.build_prompt(user_text, contexts)

            async for sentence in self.llm_service.stream_sentences(prompt, state.interrupt_event):
                if state.stop_event.is_set() or state.interrupt_event.is_set():
                    break
                await state.sentence_queue.put(sentence)

    async def _tts_writer_worker(self, state: UartSessionState) -> None:
        while not state.stop_event.is_set():
            try:
                sentence = await asyncio.wait_for(state.sentence_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            if state.interrupt_event.is_set():
                continue

            await asyncio.to_thread(state.tts_service.enqueue_sentence, sentence)

    async def _tts_drain_worker(self, state: UartSessionState) -> None:
        while not state.stop_event.is_set():
            if state.interrupt_event.is_set():
                await asyncio.to_thread(state.tts_service.clear_audio_queue)
                await asyncio.sleep(0.05)
                continue

            chunk = await asyncio.to_thread(state.tts_service.read_audio_chunk, 0.1)
            if not chunk:
                continue

            if state.outbound_audio_queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    state.outbound_audio_queue.get_nowait()
            await state.outbound_audio_queue.put(chunk)

    async def _serial_sender_worker(self, state: UartSessionState) -> None:
        streaming = False

        while not state.stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(state.outbound_audio_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                if streaming:
                    streaming = False
                    await self._send_control(state, event="tts_end")
                continue

            if state.interrupt_event.is_set():
                if streaming:
                    streaming = False
                    await self._send_control(state, event="tts_end")
                continue

            if not streaming:
                streaming = True
                await self._send_control(state, event="tts_start")

            try:
                device_audio = tts_audio_to_device_audio(
                    chunk,
                    codec=state.audio_codec,
                    tts_sample_rate=self.settings.sample_rate,
                    device_sample_rate=state.device_sample_rate,
                )
            except ValueError as exc:
                self._status["last_error"] = str(exc)
                logger.error("Unsupported audio codec for downlink: %s", exc)
                continue

            for offset in range(0, len(device_audio), state.frame_payload_bytes):
                part = device_audio[offset : offset + state.frame_payload_bytes]
                if not part:
                    continue
                await self._send_frame(state, frame_type=FrameType.AUDIO_DOWN, payload=part)
