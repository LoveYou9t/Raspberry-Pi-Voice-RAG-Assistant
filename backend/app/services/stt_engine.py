from __future__ import annotations

import importlib
import logging
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized in {"whisper_cpp", "whisper.cpp", "whisper-cpp"}:
        return "whisper_cpp"
    return "faster_whisper"


def _resolve_binary(name_or_path: str, alternatives: tuple[str, ...]) -> str | None:
    explicit_path = Path(name_or_path)
    if explicit_path.exists():
        return str(explicit_path)

    resolved = shutil.which(name_or_path)
    if resolved:
        return resolved

    for candidate in alternatives:
        path_candidate = Path(candidate)
        if path_candidate.exists():
            return str(path_candidate)

        resolved_candidate = shutil.which(candidate)
        if resolved_candidate:
            return resolved_candidate

    return None


def _resolve_whisper_cpp_model_path(model_path: str, quantization: str) -> Path:
    requested = Path(model_path)
    if requested.exists():
        return requested

    quant = quantization.strip().lower()
    candidate_names = [
        f"ggml-small-{quant}.bin",
        f"ggml-small-{quant}.gguf",
        f"whisper-small-{quant}.gguf",
        f"whisper-small-{quant}.bin",
    ]

    candidate_dirs: list[Path] = []
    if str(requested.parent) and str(requested.parent) != ".":
        candidate_dirs.append(requested.parent)
    candidate_dirs.extend(
        [
            Path("/app/model_cache/models"),
            Path("/app/model_cache"),
            Path("./whisper_cache/models"),
        ]
    )

    seen_dirs: set[Path] = set()
    for directory in candidate_dirs:
        if directory in seen_dirs:
            continue
        seen_dirs.add(directory)
        for candidate_name in candidate_names:
            candidate_path = directory / candidate_name
            if candidate_path.exists():
                return candidate_path

    return requested


class _BaseProvider:
    provider_name = "mock"
    backend_name = "mock"

    def __init__(self) -> None:
        self.available = False
        self.error = ""

    def transcribe(self, audio_f32: np.ndarray) -> str:
        return ""

    def status(self) -> dict[str, str | bool | int | None]:
        return {
            "provider": self.provider_name,
            "backend": self.backend_name if self.available else "mock",
            "available": self.available,
            "error": self.error,
        }


class _FasterWhisperProvider(_BaseProvider):
    provider_name = "faster_whisper"
    backend_name = "faster-whisper"

    def __init__(
        self,
        model_name: str,
        min_silence_ms: int,
        threshold: float,
        compute_type: str,
    ) -> None:
        super().__init__()
        self.model_name = model_name
        self.min_silence_ms = min_silence_ms
        self.threshold = threshold
        self.compute_type = compute_type
        self.model = None

        try:
            fw_module = importlib.import_module("faster_whisper")
            WhisperModel = getattr(fw_module, "WhisperModel")
            self.model = WhisperModel(model_name, device="cpu", compute_type=compute_type)
            self.available = True
        except Exception as exc:  # pragma: no cover
            self.error = str(exc)

    def transcribe(self, audio_f32: np.ndarray) -> str:
        if self.model is None or audio_f32.size == 0:
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
            return "".join(segment.text for segment in segments).strip()
        except Exception as exc:  # pragma: no cover
            logger.error("Faster-Whisper transcription failed: %s", exc)
            return ""

    def status(self) -> dict[str, str | bool | int | None]:
        payload = super().status()
        payload.update(
            {
                "model": self.model_name,
                "compute_type": self.compute_type,
            }
        )
        return payload


class _WhisperCppProvider(_BaseProvider):
    provider_name = "whisper_cpp"
    backend_name = "whisper.cpp"

    def __init__(
        self,
        binary: str,
        model_path: str,
        quantization: str,
        threads: int,
        language: str,
    ) -> None:
        super().__init__()
        self.requested_binary = binary
        self.requested_model_path = Path(model_path)
        self.model_path = _resolve_whisper_cpp_model_path(model_path, quantization)
        self.quantization = quantization
        self.threads = max(1, threads)
        self.language = language
        self.binary_path = _resolve_binary(
            binary,
            alternatives=(
                "/app/whisper.cpp/whisper-cli",
                "/app/whisper.cpp/main",
                "whisper-cli",
                "main",
            ),
        )
        self.lock = threading.Lock()

        errors: list[str] = []
        if self.binary_path is None:
            errors.append(f"whisper.cpp binary not found: {binary}")

        if not self.model_path.exists():
            errors.append(
                "whisper.cpp model not found: "
                f"requested={self.requested_model_path} resolved={self.model_path}"
            )
        elif self.model_path != self.requested_model_path:
            logger.info(
                "whisper.cpp model path fallback: requested=%s resolved=%s",
                self.requested_model_path,
                self.model_path,
            )

        self.quant_match = self.quantization.lower() in self.model_path.name.lower()
        if self.model_path.exists() and not self.quant_match:
            logger.warning(
                "whisper.cpp model filename does not contain quantization '%s': %s",
                self.quantization,
                self.model_path.name,
            )

        self.error = "; ".join(errors)
        self.available = not errors

    @staticmethod
    def _write_wav(path: Path, audio_f32: np.ndarray, sample_rate: int = 16000) -> None:
        clipped = np.clip(audio_f32, -1.0, 1.0)
        audio_i16 = (clipped * 32767.0).astype(np.int16)

        with wave.open(str(path), "wb") as wave_file:
            wave_file.setnchannels(1)
            wave_file.setsampwidth(2)
            wave_file.setframerate(sample_rate)
            wave_file.writeframes(audio_i16.tobytes())

    def transcribe(self, audio_f32: np.ndarray) -> str:
        if not self.available or self.binary_path is None or audio_f32.size == 0:
            return ""

        with self.lock:
            with tempfile.TemporaryDirectory(prefix="whisper_cpp_") as temp_dir:
                temp_path = Path(temp_dir)
                wav_path = temp_path / "input.wav"
                output_prefix = temp_path / "output"

                self._write_wav(wav_path, audio_f32)

                command = [
                    self.binary_path,
                    "-m",
                    str(self.model_path),
                    "-f",
                    str(wav_path),
                    "-otxt",
                    "-of",
                    str(output_prefix),
                ]
                if self.language:
                    command.extend(["-l", self.language])
                if self.threads > 0:
                    command.extend(["-t", str(self.threads)])

                process = subprocess.run(  # noqa: S603
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )

                if process.returncode != 0:
                    stderr = process.stderr.decode("utf-8", errors="ignore")
                    logger.error(
                        "whisper.cpp transcription failed (exit=%s): %s",
                        process.returncode,
                        stderr[:500],
                    )
                    return ""

                text_path = Path(str(output_prefix) + ".txt")
                if not text_path.exists():
                    logger.error("whisper.cpp transcription output missing: %s", text_path)
                    return ""

                return text_path.read_text(encoding="utf-8", errors="ignore").strip()

    def status(self) -> dict[str, str | bool | int | None]:
        payload = super().status()
        payload.update(
            {
                "model": str(self.model_path),
                "requested_model": str(self.requested_model_path),
                "binary": self.binary_path or "missing",
                "quantization": self.quantization,
                "quant_match": self.quant_match,
                "threads": self.threads,
                "language": self.language,
            }
        )
        return payload


class STTService:
    """Provider-based STT service with whisper.cpp and faster-whisper support."""

    def __init__(
        self,
        sample_rate: int,
        min_silence_ms: int,
        threshold: float,
        model_name: str = "tiny",
        provider: str = "faster_whisper",
        compute_type: str = "int8",
        whisper_cpp_bin: str = "/app/whisper.cpp/whisper-cli",
        whisper_cpp_model_path: str = "/app/model_cache/models/ggml-small-q5_0.bin",
        whisper_cpp_quantization: str = "q5_0",
        whisper_cpp_threads: int = 4,
        whisper_cpp_language: str = "zh",
        whisper_cpp_fallback_to_faster: bool = True,
    ) -> None:
        self.sample_rate = sample_rate
        self.min_silence_ms = min_silence_ms
        self.threshold = threshold
        self.model_name = model_name
        self.provider_requested = _normalize_provider(provider)
        self.compute_type = compute_type
        self.backend = "mock"
        self._provider: _BaseProvider = _BaseProvider()
        self._message = ""

        if self.provider_requested == "whisper_cpp":
            whisper_cpp_provider = _WhisperCppProvider(
                binary=whisper_cpp_bin,
                model_path=whisper_cpp_model_path,
                quantization=whisper_cpp_quantization,
                threads=whisper_cpp_threads,
                language=whisper_cpp_language,
            )

            if whisper_cpp_provider.available:
                self._provider = whisper_cpp_provider
                self.backend = whisper_cpp_provider.backend_name
                logger.info(
                    "STT initialized with whisper.cpp | model=%s quant=%s",
                    whisper_cpp_model_path,
                    whisper_cpp_quantization,
                )
                return

            if whisper_cpp_fallback_to_faster:
                faster_whisper_provider = _FasterWhisperProvider(
                    model_name=model_name,
                    min_silence_ms=min_silence_ms,
                    threshold=threshold,
                    compute_type=compute_type,
                )
                self._provider = faster_whisper_provider
                self.backend = (
                    faster_whisper_provider.backend_name if faster_whisper_provider.available else "mock"
                )
                self._message = (
                    "whisper.cpp unavailable, fallback to faster-whisper"
                    if faster_whisper_provider.available
                    else "whisper.cpp unavailable and faster-whisper fallback failed"
                )
                if faster_whisper_provider.available:
                    logger.warning(
                        "%s: %s",
                        self._message,
                        whisper_cpp_provider.error,
                    )
                else:
                    logger.warning(
                        "%s | whisper.cpp error=%s | fallback error=%s",
                        self._message,
                        whisper_cpp_provider.error,
                        faster_whisper_provider.error,
                    )
                return

            self._provider = whisper_cpp_provider
            self.backend = "mock"
            self._message = "whisper.cpp unavailable and fallback disabled"
            logger.warning("%s: %s", self._message, whisper_cpp_provider.error)
            return

        faster_whisper_provider = _FasterWhisperProvider(
            model_name=model_name,
            min_silence_ms=min_silence_ms,
            threshold=threshold,
            compute_type=compute_type,
        )
        self._provider = faster_whisper_provider
        self.backend = faster_whisper_provider.backend_name if faster_whisper_provider.available else "mock"

        if faster_whisper_provider.available:
            logger.info(
                "STT initialized with Faster-Whisper | model=%s compute=%s",
                model_name,
                compute_type,
            )
        else:
            logger.warning("Faster-Whisper unavailable, STT fallback enabled: %s", faster_whisper_provider.error)

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""

        audio_i16 = np.frombuffer(audio_bytes, dtype=np.int16)
        if audio_i16.size == 0:
            return ""

        audio_f32 = audio_i16.astype(np.float32) / 32768.0
        return self._provider.transcribe(audio_f32)

    def status(self) -> dict[str, str | bool | int | None]:
        payload = self._provider.status()
        payload.update(
            {
                "requested_provider": self.provider_requested,
                "active_backend": self.backend,
                "sample_rate": self.sample_rate,
                "message": self._message,
            }
        )
        return payload
