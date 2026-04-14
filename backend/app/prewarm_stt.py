from __future__ import annotations

import json
import os
import time
from pathlib import Path


DEFAULT_STATUS_PATH = "/app/model_cache/stt_prewarm_status.json"


def _is_true(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _write_status(status_path: Path, status: dict) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status["timestamp"] = int(time.time())
    status_path.write_text(json.dumps(status, ensure_ascii=True, indent=2), encoding="utf-8")


def main() -> int:
    model_name = os.getenv("STT_MODEL", "tiny")
    strict_mode = _is_true(os.getenv("STT_PREWARM_STRICT"))
    status_path = Path(os.getenv("STT_PREWARM_STATUS_FILE", DEFAULT_STATUS_PATH))

    print(f"Prewarming Faster-Whisper model: {model_name}")
    try:
        from faster_whisper import WhisperModel

        WhisperModel(model_name, device="cpu", compute_type="int8")
        _write_status(
            status_path,
            {
                "ok": True,
                "component": "stt",
                "model": model_name,
                "message": "stt prewarm completed",
            },
        )
    except Exception as exc:
        message = f"Faster-Whisper prewarm skipped: {exc}"
        print(f"Warning: {message}")
        print("Service will continue startup; model can be downloaded on first use.")
        _write_status(
            status_path,
            {
                "ok": False,
                "component": "stt",
                "model": model_name,
                "message": message,
            },
        )
        if strict_mode:
            return 1
        return 0
    print("Faster-Whisper prewarm completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
