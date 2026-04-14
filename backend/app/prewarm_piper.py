from __future__ import annotations

import logging
import os
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx

LOGGER = logging.getLogger("prewarm_piper")

DEFAULT_MODEL_PATH = "/app/piper_cache/zh_CN-huayan-medium.onnx"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
)
DEFAULT_STATUS_PATH = "/app/piper_cache/piper_prewarm_status.json"


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


def _resolve_piper_binary(name_or_path: str) -> str:
    direct_path = Path(name_or_path)
    if direct_path.exists():
        return str(direct_path)

    resolved = shutil.which(name_or_path)
    if resolved:
        return resolved

    raise RuntimeError(f"Piper binary not found: {name_or_path}")


def _is_true(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _write_status(status_path: Path, status: dict) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status["timestamp"] = int(time.time())
    status_path.write_text(json.dumps(status, ensure_ascii=True, indent=2), encoding="utf-8")


def _download_with_retry(
    url: str,
    target_path: Path,
    max_attempts: int,
    retry_seconds: int,
    timeout_seconds: float,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".part")

    for attempt in range(1, max_attempts + 1):
        try:
            LOGGER.info("Downloading %s (attempt %s/%s)", url, attempt, max_attempts)
            with httpx.stream("GET", url, follow_redirects=True, timeout=timeout_seconds) as response:
                response.raise_for_status()
                with temp_path.open("wb") as file_obj:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if chunk:
                            file_obj.write(chunk)

            if temp_path.stat().st_size <= 0:
                raise RuntimeError(f"Downloaded file is empty: {target_path}")

            temp_path.replace(target_path)
            LOGGER.info("Downloaded to %s", target_path)
            return
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Download failed: %s", exc)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if attempt == max_attempts:
                raise
            time.sleep(retry_seconds)


def _ensure_file(
    target_path: Path,
    source_url: str,
    max_attempts: int,
    retry_seconds: int,
    timeout_seconds: float,
) -> None:
    if target_path.exists() and target_path.stat().st_size > 0:
        LOGGER.info("Already present: %s", target_path)
        return
    _download_with_retry(source_url, target_path, max_attempts, retry_seconds, timeout_seconds)


def _run_smoke_test(piper_bin: str, model_path: Path, model_config_path: Path) -> None:
    command = [
        piper_bin,
        "--model",
        str(model_path),
        "--config",
        str(model_config_path),
        "--output-raw",
    ]
    process = subprocess.run(  # noqa: S603
        command,
        input=b"Piper smoke test sentence.\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if process.returncode != 0:
        stderr = process.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"Piper smoke test failed (exit={process.returncode}): {stderr}")

    if not process.stdout:
        raise RuntimeError("Piper smoke test produced empty audio output")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    piper_bin = _resolve_piper_binary(os.getenv("PIPER_BIN", "piper"))
    model_path = Path(os.getenv("PIPER_MODEL", DEFAULT_MODEL_PATH))
    model_url = os.getenv("PIPER_MODEL_URL", DEFAULT_MODEL_URL)

    model_config_path = Path(os.getenv("PIPER_MODEL_CONFIG", f"{model_path}.json"))
    model_config_url = os.getenv("PIPER_MODEL_CONFIG_URL", f"{model_url}.json")
    status_path = Path(os.getenv("PIPER_PREWARM_STATUS_FILE", DEFAULT_STATUS_PATH))

    max_attempts = _get_int("PIPER_DOWNLOAD_MAX_ATTEMPTS", 5)
    retry_seconds = _get_int("PIPER_DOWNLOAD_RETRY_SECONDS", 2)
    timeout_seconds = _get_float("PIPER_DOWNLOAD_TIMEOUT_SECONDS", 120.0)

    LOGGER.info("Piper binary: %s", piper_bin)
    LOGGER.info("Model path: %s", model_path)
    LOGGER.info("Config path: %s", model_config_path)

    _ensure_file(model_path, model_url, max_attempts, retry_seconds, timeout_seconds)
    _ensure_file(model_config_path, model_config_url, max_attempts, retry_seconds, timeout_seconds)

    LOGGER.info("Running Piper smoke test...")
    _run_smoke_test(piper_bin, model_path, model_config_path)
    _write_status(
        status_path,
        {
            "ok": True,
            "component": "piper",
            "model_path": str(model_path),
            "config_path": str(model_config_path),
            "message": "piper prewarm completed",
        },
    )
    LOGGER.info("Piper prewarm completed.")


if __name__ == "__main__":
    strict_mode = _is_true(os.getenv("PIPER_PREWARM_STRICT"))
    status_path = Path(os.getenv("PIPER_PREWARM_STATUS_FILE", DEFAULT_STATUS_PATH))

    try:
        main()
    except Exception:  # noqa: BLE001
        LOGGER.exception("Piper prewarm failed")
        _write_status(
            status_path,
            {
                "ok": False,
                "component": "piper",
                "message": "piper prewarm failed",
            },
        )
        raise SystemExit(1 if strict_mode else 0)
