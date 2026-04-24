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


def _get_csv(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    values = [item.strip() for item in raw.split(",")]
    return tuple(item for item in values if item)


def _get_csv_int(name: str, default: str) -> tuple[int, ...]:
    output: list[int] = []
    for item in _get_csv(name, default):
        try:
            output.append(int(item))
        except ValueError:
            continue
    return tuple(output)


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = _get_int("APP_PORT", 8000)
    ws_path: str = os.getenv("WS_PATH", "/ws/audio-stream")
    transport_default_mode: str = os.getenv("TRANSPORT_DEFAULT_MODE", "wifi")
    transport_config_path: str = os.getenv(
        "TRANSPORT_CONFIG_PATH", "/app/lancedb_data/transport_config.json"
    )
    bluetooth_default_port: str = os.getenv("BLUETOOTH_DEFAULT_PORT", "/dev/rfcomm0")
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
    llm_keep_alive: str = os.getenv("LLM_KEEP_ALIVE", "24h")
    llm_warmup_on_startup: bool = _get_bool("LLM_WARMUP_ON_STARTUP", True)
    llm_warmup_prompt: str = os.getenv("LLM_WARMUP_PROMPT", "你好")
    llm_warmup_timeout_seconds: float = _get_float("LLM_WARMUP_TIMEOUT_SECONDS", 30.0)
    llm_warmup_retries: int = _get_int("LLM_WARMUP_RETRIES", 2)
    llm_warmup_retry_delay_seconds: float = _get_float("LLM_WARMUP_RETRY_DELAY_SECONDS", 2.0)
    llm_keepalive_enabled: bool = _get_bool("LLM_KEEPALIVE_ENABLED", True)
    llm_keepalive_interval_seconds: int = _get_int("LLM_KEEPALIVE_INTERVAL_SECONDS", 300)
    llm_keepalive_prompt: str = os.getenv("LLM_KEEPALIVE_PROMPT", "嗯")

    stt_provider: str = os.getenv("STT_PROVIDER", "whisper_cpp")
    stt_model: str = os.getenv("STT_MODEL", "tiny")
    stt_compute_type: str = os.getenv("STT_COMPUTE_TYPE", "int8")
    stt_cpp_bin: str = os.getenv("STT_CPP_BIN", "/app/whisper.cpp/whisper-cli")
    stt_cpp_model_path: str = os.getenv(
        "STT_CPP_MODEL_PATH", "/app/model_cache/models/ggml-small-q5_0.bin"
    )
    stt_cpp_quant: str = os.getenv("STT_CPP_QUANT", "q5_0")
    stt_cpp_threads: int = _get_int("STT_CPP_THREADS", 4)
    stt_cpp_language: str = os.getenv("STT_CPP_LANGUAGE", "zh")
    stt_cpp_fallback_to_faster: bool = _get_bool("STT_CPP_FALLBACK_TO_FASTER", True)

    sample_rate: int = _get_int("SAMPLE_RATE", 16000)
    audio_chunk_seconds: float = _get_float("AUDIO_CHUNK_SECONDS", 1.0)
    ws_supported_audio_codecs: tuple[str, ...] = _get_csv(
        "WS_SUPPORTED_AUDIO_CODECS", "opus,pcm16"
    )
    ws_supported_sample_rates: tuple[int, ...] = _get_csv_int(
        "WS_SUPPORTED_SAMPLE_RATES", "16000,24000,48000"
    )
    ws_default_audio_codec: str = os.getenv("WS_DEFAULT_AUDIO_CODEC", "opus")
    ws_default_uplink_sample_rate: int = _get_int("WS_DEFAULT_UPLINK_SAMPLE_RATE", 16000)
    ws_default_downlink_sample_rate: int = _get_int("WS_DEFAULT_DOWNLINK_SAMPLE_RATE", 16000)
    ws_opus_frame_ms: int = _get_int("WS_OPUS_FRAME_MS", 20)
    ws_opus_bitrate: int = _get_int("WS_OPUS_BITRATE", 24000)

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
    stt_prewarm_status_file: str = os.getenv(
        "STT_PREWARM_STATUS_FILE", "/app/model_cache/stt_prewarm_status.json"
    )
    piper_prewarm_status_file: str = os.getenv(
        "PIPER_PREWARM_STATUS_FILE", "/app/piper_cache/piper_prewarm_status.json"
    )


settings = Settings()
