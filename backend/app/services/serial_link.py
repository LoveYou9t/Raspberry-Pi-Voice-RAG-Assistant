from __future__ import annotations

import importlib
import threading

serial = None


class SerialTransportError(RuntimeError):
    pass


def _load_serial_module():
    global serial

    if serial is not None:
        return serial

    try:
        serial = importlib.import_module("serial")
    except Exception as exc:  # pragma: no cover
        raise SerialTransportError("pyserial is required for UART mode") from exc
    return serial


class SerialTransport:
    def __init__(
        self,
        port: str,
        baudrate: int,
        timeout_seconds: float,
        write_timeout_seconds: float,
        read_size: int,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.write_timeout_seconds = write_timeout_seconds
        self.read_size = read_size

        self._serial = None
        self._write_lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def open(self) -> None:
        if self.is_open:
            return

        serial_module = _load_serial_module()

        try:
            self._serial = serial_module.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout_seconds,
                write_timeout=self.write_timeout_seconds,
            )
        except Exception as exc:
            raise SerialTransportError(f"failed to open serial port {self.port}: {exc}") from exc

    def close(self) -> None:
        if self._serial is None:
            return

        try:
            self._serial.close()
        except Exception:
            pass
        finally:
            self._serial = None

    def read(self, size: int | None = None) -> bytes:
        if not self.is_open or self._serial is None:
            return b""

        read_size = size or self.read_size
        try:
            return self._serial.read(read_size)
        except Exception as exc:
            raise SerialTransportError(f"serial read failed: {exc}") from exc

    def write(self, payload: bytes) -> int:
        if not payload:
            return 0
        if not self.is_open or self._serial is None:
            raise SerialTransportError("serial port is not open")

        with self._write_lock:
            try:
                written = self._serial.write(payload)
                self._serial.flush()
                return written
            except Exception as exc:
                raise SerialTransportError(f"serial write failed: {exc}") from exc
