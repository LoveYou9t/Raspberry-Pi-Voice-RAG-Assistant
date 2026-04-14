from __future__ import annotations

import os


def main() -> int:
    model_name = os.getenv("STT_MODEL", "tiny")
    print(f"Prewarming Faster-Whisper model: {model_name}")
    try:
        from faster_whisper import WhisperModel

        WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as exc:
        print(f"Warning: Faster-Whisper prewarm skipped: {exc}")
        print("Service will continue startup; model can be downloaded on first use.")
        return 0
    print("Faster-Whisper prewarm completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
