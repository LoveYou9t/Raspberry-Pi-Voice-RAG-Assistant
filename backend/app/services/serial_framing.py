from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

MAGIC = b"\xAA\x55"
PROTOCOL_VERSION = 1
_HEADER_STRUCT = struct.Struct("!2sBBBHH")
_CRC_STRUCT = struct.Struct("!H")
_HEADER_SIZE = _HEADER_STRUCT.size
_CRC_SIZE = _CRC_STRUCT.size
_MIN_FRAME_SIZE = _HEADER_SIZE + _CRC_SIZE


class FrameType(IntEnum):
    CONTROL = 1
    AUDIO_UP = 2
    AUDIO_DOWN = 3
    ACK = 4
    HEARTBEAT = 5
    STATUS = 6


@dataclass(frozen=True)
class SerialFrame:
    frame_type: int
    seq: int
    flags: int
    payload: bytes


def crc16_ccitt(data: bytes, seed: int = 0xFFFF) -> int:
    crc = seed
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode_frame(frame_type: int, seq: int, payload: bytes = b"", flags: int = 0) -> bytes:
    payload_len = len(payload)
    if payload_len > 0xFFFF:
        raise ValueError("payload too large")

    header = _HEADER_STRUCT.pack(
        MAGIC,
        PROTOCOL_VERSION,
        int(frame_type) & 0xFF,
        flags & 0xFF,
        seq & 0xFFFF,
        payload_len,
    )
    crc = crc16_ccitt(header + payload)
    return header + payload + _CRC_STRUCT.pack(crc)


class FrameParser:
    def __init__(self, max_payload_size: int = 2048) -> None:
        self.max_payload_size = max_payload_size
        self.buffer = bytearray()
        self.crc_errors = 0
        self.dropped_bytes = 0

    def feed(self, data: bytes) -> list[SerialFrame]:
        if data:
            self.buffer.extend(data)

        frames: list[SerialFrame] = []
        while len(self.buffer) >= _MIN_FRAME_SIZE:
            magic_pos = self.buffer.find(MAGIC)
            if magic_pos < 0:
                self.dropped_bytes += len(self.buffer)
                self.buffer.clear()
                break

            if magic_pos > 0:
                self.dropped_bytes += magic_pos
                del self.buffer[:magic_pos]
                if len(self.buffer) < _MIN_FRAME_SIZE:
                    break

            try:
                _, version, frame_type, flags, seq, payload_len = _HEADER_STRUCT.unpack(
                    self.buffer[:_HEADER_SIZE]
                )
            except struct.error:
                break

            if version != PROTOCOL_VERSION:
                self.dropped_bytes += 1
                del self.buffer[0]
                continue

            if payload_len > self.max_payload_size:
                self.dropped_bytes += 1
                del self.buffer[0]
                continue

            frame_len = _HEADER_SIZE + payload_len + _CRC_SIZE
            if len(self.buffer) < frame_len:
                break

            packet = bytes(self.buffer[:frame_len])
            del self.buffer[:frame_len]

            expected_crc = _CRC_STRUCT.unpack(packet[-_CRC_SIZE:])[0]
            calculated_crc = crc16_ccitt(packet[:-_CRC_SIZE])
            if expected_crc != calculated_crc:
                self.crc_errors += 1
                continue

            payload = packet[_HEADER_SIZE : _HEADER_SIZE + payload_len]
            frames.append(SerialFrame(frame_type=frame_type, seq=seq, flags=flags, payload=payload))

        return frames
