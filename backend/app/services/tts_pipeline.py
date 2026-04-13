from __future__ import annotations

import logging
import math
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class PiperTTSService:
    """Persistent Piper process with non-blocking queue bridge."""

    def __init__(
        self,
        piper_bin: str,
        model_path: str,
        sample_rate: int,
        chunk_size: int,
        allow_mock_on_missing: bool,
    ) -> None:
        self.piper_bin = piper_bin
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.allow_mock_on_missing = allow_mock_on_missing

        self.process: Optional[subprocess.Popen] = None
        self.output_queue: queue.Queue[bytes] = queue.Queue(maxsize=256)
        self.stop_event = threading.Event()
        self.reader_thread: Optional[threading.Thread] = None
        self.use_mock = False

    def start(self) -> None:
        binary = self._resolve_binary(self.piper_bin)
        if binary is None:
            self.use_mock = self.allow_mock_on_missing
            logger.warning("Piper binary not found, using mock audio: %s", self.use_mock)
            return

        command = [binary, "--model", self.model_path, "--output-raw"]
        if not Path(self.model_path).exists():
            logger.warning("Piper model path not found: %s", self.model_path)

        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        logger.info("Piper TTS service started.")

    @staticmethod
    def _resolve_binary(name_or_path: str) -> Optional[str]:
        explicit_path = Path(name_or_path)
        if explicit_path.exists():
            return str(explicit_path)
        return shutil.which(name_or_path)

    def _reader_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.process is None or self.process.stdout is None:
                break

            chunk = self.process.stdout.read(self.chunk_size)
            if not chunk:
                if self.process.poll() is not None:
                    logger.error("Piper process exited unexpectedly.")
                    break
                continue

            self._offer_audio(chunk)

    def _offer_audio(self, chunk: bytes) -> None:
        try:
            self.output_queue.put(chunk, timeout=0.05)
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.output_queue.put_nowait(chunk)
            except queue.Full:
                pass

    def enqueue_sentence(self, sentence: str) -> None:
        text = sentence.strip()
        if not text:
            return

        if self.use_mock or self.process is None or self.process.stdin is None:
            self._enqueue_mock_audio(text)
            return

        try:
            self.process.stdin.write((text + "\n").encode("utf-8"))
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            logger.exception("Failed to write sentence to Piper stdin.")
            if self.allow_mock_on_missing:
                self.use_mock = True
                self._enqueue_mock_audio(text)

    def _enqueue_mock_audio(self, text: str) -> None:
        duration = min(1.5, 0.25 + 0.02 * len(text))
        sample_count = int(self.sample_rate * duration)
        if sample_count <= 0:
            return

        t = np.arange(sample_count, dtype=np.float32) / float(self.sample_rate)
        wave = 0.15 * np.sin(2.0 * math.pi * 220.0 * t)
        pcm = (wave * 32767.0).astype(np.int16).tobytes()

        for i in range(0, len(pcm), self.chunk_size):
            self._offer_audio(pcm[i : i + self.chunk_size])

    def read_audio_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        try:
            return self.output_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_audio_queue(self) -> None:
        while True:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self.stop_event.set()
        self.clear_audio_queue()

        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                self.process.kill()
