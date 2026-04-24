from __future__ import annotations

import audioop

try:
    import opuslib
except ImportError:  # pragma: no cover - optional dependency
    opuslib = None


class OpusUnavailableError(RuntimeError):
    pass


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


def opus_available() -> bool:
    return opuslib is not None


class OpusPcm16Encoder:
    def __init__(self, sample_rate: int, channels: int = 1, bitrate: int = 24000) -> None:
        if opuslib is None:
            raise OpusUnavailableError("opuslib is not installed")
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate
        self._encoder = opuslib.Encoder(sample_rate, channels, "audio")
        self._encoder.bitrate = bitrate

    def encode(self, pcm_frame: bytes, frame_size_samples: int) -> bytes:
        pcm_frame = _trim_pcm16(pcm_frame)
        if not pcm_frame:
            return b""
        return self._encoder.encode(pcm_frame, frame_size_samples)


class OpusPcm16Decoder:
    def __init__(self, sample_rate: int, channels: int = 1) -> None:
        if opuslib is None:
            raise OpusUnavailableError("opuslib is not installed")
        self.sample_rate = sample_rate
        self.channels = channels
        self._decoder = opuslib.Decoder(sample_rate, channels)

    def decode(self, opus_packet: bytes, frame_size_samples: int) -> bytes:
        if not opus_packet:
            return b""
        return self._decoder.decode(opus_packet, frame_size_samples)
