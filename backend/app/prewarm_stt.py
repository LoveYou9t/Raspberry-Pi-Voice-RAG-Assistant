from __future__ import annotations

import os

from faster_whisper import WhisperModel


if __name__ == "__main__":
    model_name = os.getenv("STT_MODEL", "tiny")
    print(f"Prewarming Faster-Whisper model: {model_name}")
    WhisperModel(model_name, device="cpu", compute_type="int8")
    print("Faster-Whisper prewarm completed")
