from __future__ import annotations

import importlib
import logging

import numpy as np

logger = logging.getLogger(__name__)


class STTService:
    """Faster-Whisper based STT with optional runtime fallback."""

    def __init__(
        self,
        sample_rate: int,
        min_silence_ms: int,
        threshold: float,
        model_name: str = "distil-large-v3",
    ) -> None:
        self.sample_rate = sample_rate
        self.min_silence_ms = min_silence_ms
        self.threshold = threshold
        self.model_name = model_name
        self.model = None
        self.backend = "mock"

        try:
            fw_module = importlib.import_module("faster_whisper")
            WhisperModel = getattr(fw_module, "WhisperModel")

            self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
            self.backend = "faster-whisper"
            logger.info("STT initialized with Faster-Whisper model: %s", model_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("Faster-Whisper unavailable, STT fallback enabled: %s", exc)

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""

        audio_i16 = np.frombuffer(audio_bytes, dtype=np.int16)
        if audio_i16.size == 0:
            return ""

        audio_f32 = audio_i16.astype(np.float32) / 32768.0

        if self.model is None:
            return ""

        try:
            segments, _ = self.model.transcribe(
                audio_f32,
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": self.min_silence_ms,
                    "threshold": self.threshold,
                },
            )
            text = "".join(segment.text for segment in segments).strip()
            return text
        except Exception as exc:  # pragma: no cover
            logger.error("STT transcription failed: %s", exc)
            return ""
