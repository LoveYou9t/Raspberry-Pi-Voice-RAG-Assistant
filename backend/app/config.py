from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = _get_int("APP_PORT", 8000)
    ws_path: str = os.getenv("WS_PATH", "/ws/audio-stream")
    uart_enabled: bool = _get_bool("UART_ENABLED", False)
    uart_port: str = os.getenv("UART_PORT", "/dev/ttyAMA0")
    uart_baudrate: int = _get_int("UART_BAUDRATE", 115200)
    uart_timeout_ms: int = _get_int("UART_TIMEOUT_MS", 50)
    uart_read_size: int = _get_int("UART_READ_SIZE", 1024)
    uart_frame_payload_bytes: int = _get_int("UART_FRAME_PAYLOAD_BYTES", 240)
    uart_audio_codec: str = os.getenv("UART_AUDIO_CODEC", "ulaw8k")
    uart_device_sample_rate: int = _get_int("UART_DEVICE_SAMPLE_RATE", 8000)

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    llm_model: str = os.getenv("LLM_MODEL", "llama3.2:3b")
    llm_num_ctx: int = _get_int("LLM_NUM_CTX", 4096)
    llm_temperature: float = _get_float("LLM_TEMPERATURE", 0.3)
    llm_top_k: int = _get_int("LLM_TOP_K", 40)
    stt_model: str = os.getenv("STT_MODEL", "tiny")

    sample_rate: int = _get_int("SAMPLE_RATE", 16000)
    audio_chunk_seconds: float = _get_float("AUDIO_CHUNK_SECONDS", 1.0)

    vad_min_silence_ms: int = _get_int("VAD_MIN_SILENCE_MS", 500)
    vad_threshold: float = _get_float("VAD_THRESHOLD", 0.4)

    rag_top_k: int = _get_int("RAG_TOP_K", 3)
    knowledge_dir: str = os.getenv("KNOWLEDGE_DIR", "/app/knowledge_base")
    lancedb_dir: str = os.getenv("LANCEDB_DIR", "/app/lancedb_data")
    lancedb_table: str = os.getenv("LANCEDB_TABLE", "knowledge_base_vectors")
    vector_dim: int = _get_int("VECTOR_DIM", 384)

    piper_bin: str = os.getenv("PIPER_BIN", "piper")
    piper_model: str = os.getenv("PIPER_MODEL", "/app/piper_cache/zh_CN-huayan-medium.onnx")
    piper_chunk_size: int = _get_int("PIPER_CHUNK_SIZE", 4096)
    piper_use_mock_on_missing: bool = _get_bool("PIPER_USE_MOCK_ON_MISSING", False)


settings = Settings()
