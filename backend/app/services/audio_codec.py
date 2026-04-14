from __future__ import annotations

import audioop


def _trim_pcm16(payload: bytes) -> bytes:
    if len(payload) % 2 == 0:
        return payload
    return payload[:-1]


def resample_pcm16(payload: bytes, source_rate: int, target_rate: int) -> bytes:
    payload = _trim_pcm16(payload)
    if not payload or source_rate == target_rate:
        return payload

    converted, _ = audioop.ratecv(payload, 2, 1, source_rate, target_rate, None)
    return converted


def device_audio_to_stt_audio(
    payload: bytes,
    codec: str,
    device_sample_rate: int,
    stt_sample_rate: int,
) -> bytes:
    normalized = codec.lower()
    if normalized == "ulaw8k":
        pcm = audioop.ulaw2lin(payload, 2)
    elif normalized in {"pcm16", "pcm16le"}:
        pcm = _trim_pcm16(payload)
    else:
        raise ValueError(f"unsupported uart audio codec: {codec}")

    return resample_pcm16(pcm, device_sample_rate, stt_sample_rate)


def tts_audio_to_device_audio(
    payload: bytes,
    codec: str,
    tts_sample_rate: int,
    device_sample_rate: int,
) -> bytes:
    pcm = resample_pcm16(payload, tts_sample_rate, device_sample_rate)

    normalized = codec.lower()
    if normalized == "ulaw8k":
        return audioop.lin2ulaw(pcm, 2)
    if normalized in {"pcm16", "pcm16le"}:
        return pcm
    raise ValueError(f"unsupported uart audio codec: {codec}")
