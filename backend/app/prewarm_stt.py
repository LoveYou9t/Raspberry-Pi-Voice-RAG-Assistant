from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path


DEFAULT_STATUS_PATH = "/app/model_cache/stt_prewarm_status.json"


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized in {"whisper_cpp", "whisper.cpp", "whisper-cpp"}:
        return "whisper_cpp"
    return "faster_whisper"


def _is_true(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _write_status(status_path: Path, status: dict) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status["timestamp"] = int(time.time())
    status_path.write_text(json.dumps(status, ensure_ascii=True, indent=2), encoding="utf-8")


def _resolve_whisper_cpp_binary(name_or_path: str) -> str:
    explicit_path = Path(name_or_path)
    if explicit_path.exists():
        return str(explicit_path)

    resolved = shutil.which(name_or_path)
    if resolved:
        return resolved

    for candidate in (
        "/app/whisper.cpp/whisper-cli",
        "/app/whisper.cpp/main",
        "whisper-cli",
        "main",
    ):
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return str(candidate_path)

        resolved_candidate = shutil.which(candidate)
        if resolved_candidate:
            return resolved_candidate

    raise RuntimeError(f"whisper.cpp binary not found: {name_or_path}")


def _resolve_whisper_cpp_model_path(model_path: Path, quantization: str) -> Path:
    if model_path.exists():
        return model_path

    quant = quantization.strip().lower()
    candidate_names = [
        f"ggml-small-{quant}.bin",
        f"ggml-small-{quant}.gguf",
        f"whisper-small-{quant}.gguf",
        f"whisper-small-{quant}.bin",
    ]
    candidate_dirs = [
        model_path.parent,
        Path("/app/model_cache/models"),
        Path("/app/model_cache"),
        Path("./whisper_cache/models"),
    ]

    seen_dirs: set[Path] = set()
    for directory in candidate_dirs:
        if directory in seen_dirs:
            continue
        seen_dirs.add(directory)
        for candidate_name in candidate_names:
            candidate_path = directory / candidate_name
            if candidate_path.exists():
                print(
                    "whisper.cpp model path fallback "
                    f"requested={model_path} resolved={candidate_path}"
                )
                return candidate_path

    return model_path


def _write_silence_wav(path: Path, sample_rate: int = 16000, duration_seconds: float = 0.6) -> None:
    frame_count = max(1, int(sample_rate * duration_seconds))
    silence = b"\x00\x00" * frame_count

    with wave.open(str(path), "wb") as wave_file:
        wave_file.setnchannels(1)
        wave_file.setsampwidth(2)
        wave_file.setframerate(sample_rate)
        wave_file.writeframes(silence)


def _prewarm_faster_whisper(model_name: str, compute_type: str) -> None:
    from faster_whisper import WhisperModel

    WhisperModel(model_name, device="cpu", compute_type=compute_type)


def _prewarm_whisper_cpp(
    binary_name_or_path: str,
    model_path: Path,
    language: str,
    threads: int,
    quantization: str,
) -> Path:
    binary_path = _resolve_whisper_cpp_binary(binary_name_or_path)
    model_path = _resolve_whisper_cpp_model_path(model_path, quantization)
    if not model_path.exists():
        raise RuntimeError(f"whisper.cpp model not found: {model_path}")

    if quantization and quantization.lower() not in model_path.name.lower():
        print(
            "Warning: model filename does not include configured quantization "
            f"'{quantization}': {model_path.name}"
        )

    with tempfile.TemporaryDirectory(prefix="prewarm_whisper_cpp_") as temp_dir:
        temp_path = Path(temp_dir)
        wav_path = temp_path / "smoke.wav"
        output_prefix = temp_path / "smoke"
        _write_silence_wav(wav_path)

        command = [
            binary_path,
            "-m",
            str(model_path),
            "-f",
            str(wav_path),
            "-otxt",
            "-of",
            str(output_prefix),
        ]
        if language:
            command.extend(["-l", language])
        if threads > 0:
            command.extend(["-t", str(max(1, threads))])

        process = subprocess.run(  # noqa: S603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if process.returncode != 0:
            stderr = process.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"whisper.cpp smoke test failed (exit={process.returncode}): {stderr[:500]}"
            )

        text_path = Path(str(output_prefix) + ".txt")
        if not text_path.exists():
            raise RuntimeError(f"whisper.cpp smoke test output missing: {text_path}")

    return model_path


def main() -> int:
    model_name = os.getenv("STT_MODEL", "tiny")
    provider = _normalize_provider(os.getenv("STT_PROVIDER", "faster_whisper"))
    compute_type = os.getenv("STT_COMPUTE_TYPE", "int8")
    stt_cpp_bin = os.getenv("STT_CPP_BIN", "/app/whisper.cpp/whisper-cli")
    stt_cpp_model_path = Path(
        os.getenv("STT_CPP_MODEL_PATH", "/app/model_cache/models/ggml-small-q5_0.bin")
    )
    stt_cpp_quant = os.getenv("STT_CPP_QUANT", "q5_0")
    stt_cpp_threads = int(os.getenv("STT_CPP_THREADS", "4") or "4")
    stt_cpp_language = os.getenv("STT_CPP_LANGUAGE", "zh")
    stt_cpp_fallback_to_faster = _is_true(os.getenv("STT_CPP_FALLBACK_TO_FASTER", "1"))

    strict_mode = _is_true(os.getenv("STT_PREWARM_STRICT"))
    status_path = Path(os.getenv("STT_PREWARM_STATUS_FILE", DEFAULT_STATUS_PATH))

    requested_backend = "whisper.cpp" if provider == "whisper_cpp" else "faster-whisper"
    active_backend = "mock"
    ok = False

    print(f"Prewarming STT provider: {provider}")
    resolved_whisper_cpp_model_path = stt_cpp_model_path

    try:
        if provider == "whisper_cpp":
            resolved_whisper_cpp_model_path = _prewarm_whisper_cpp(
                binary_name_or_path=stt_cpp_bin,
                model_path=stt_cpp_model_path,
                language=stt_cpp_language,
                threads=stt_cpp_threads,
                quantization=stt_cpp_quant,
            )
            active_backend = "whisper.cpp"
            ok = True
            message = "whisper.cpp prewarm completed"
        else:
            _prewarm_faster_whisper(model_name=model_name, compute_type=compute_type)
            active_backend = "faster-whisper"
            ok = True
            message = "faster-whisper prewarm completed"

    except Exception as exc:
        if provider == "whisper_cpp" and stt_cpp_fallback_to_faster:
            primary_error = str(exc)
            print(f"Warning: whisper.cpp prewarm failed: {primary_error}")
            print("Trying faster-whisper fallback prewarm...")
            try:
                _prewarm_faster_whisper(model_name=model_name, compute_type=compute_type)
                active_backend = "faster-whisper"
                ok = False
                message = (
                    "whisper.cpp prewarm failed, faster-whisper fallback is available: "
                    f"{primary_error}"
                )
            except Exception as fallback_exc:
                active_backend = "mock"
                ok = False
                message = (
                    "whisper.cpp prewarm failed and faster-whisper fallback failed: "
                    f"primary={primary_error}; fallback={fallback_exc}"
                )
        else:
            active_backend = "mock"
            ok = False
            message = f"stt prewarm failed: {exc}"

    _write_status(
        status_path,
        {
            "ok": ok,
            "component": "stt",
            "requested_provider": provider,
            "requested_backend": requested_backend,
            "backend": active_backend,
            "model": model_name,
            "compute_type": compute_type,
            "whisper_cpp_model": str(resolved_whisper_cpp_model_path),
            "whisper_cpp_requested_model": str(stt_cpp_model_path),
            "whisper_cpp_quant": stt_cpp_quant,
            "message": message,
        },
    )

    if ok:
        print(message)
        return 0

    print(f"Warning: {message}")
    print("Service will continue startup when strict mode is disabled.")
    if strict_mode:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
