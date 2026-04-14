from __future__ import annotations

import logging
import os
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterable

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


def _parse_fallback_urls(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []

    urls: list[str] = []
    for item in raw_value.split(","):
        candidate = item.strip()
        if candidate:
            urls.append(candidate)
    return urls


def _dedupe_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def _download_once(
    url: str,
    target_path: Path,
    timeout_seconds: float,
    trust_env: bool,
    local_address: str | None,
) -> None:
    temp_path = target_path.with_suffix(target_path.suffix + ".part")

    transport = None
    if local_address:
        transport = httpx.HTTPTransport(local_address=local_address)

    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        trust_env=trust_env,
        transport=transport,
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with temp_path.open("wb") as file_obj:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if chunk:
                        file_obj.write(chunk)

    if temp_path.stat().st_size <= 0:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file is empty: {target_path}")

    temp_path.replace(target_path)


def _download_with_retry(
    urls: list[str],
    target_path: Path,
    max_attempts: int,
    retry_seconds: int,
    timeout_seconds: float,
    trust_env: bool,
    local_address: str | None,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not urls:
        raise RuntimeError("No download URLs provided")

    errors: list[str] = []
    for url in urls:
        for attempt in range(1, max_attempts + 1):
            try:
                LOGGER.info("Downloading %s (attempt %s/%s)", url, attempt, max_attempts)
                _download_once(
                    url=url,
                    target_path=target_path,
                    timeout_seconds=timeout_seconds,
                    trust_env=trust_env,
                    local_address=local_address,
                )
                LOGGER.info("Downloaded to %s", target_path)
                return
            except Exception as exc:  # noqa: BLE001
                message = f"url={url} attempt={attempt}/{max_attempts} error={exc}"
                errors.append(message)
                LOGGER.warning("Download failed: %s", message)
                part_file = target_path.with_suffix(target_path.suffix + ".part")
                if part_file.exists():
                    part_file.unlink(missing_ok=True)
                if attempt < max_attempts:
                    time.sleep(retry_seconds)

    raise RuntimeError("; ".join(errors[-6:]))


def _ensure_file(
    target_path: Path,
    source_urls: list[str],
    max_attempts: int,
    retry_seconds: int,
    timeout_seconds: float,
    trust_env: bool,
    local_address: str | None,
) -> None:
    if target_path.exists() and target_path.stat().st_size > 0:
        LOGGER.info("Already present: %s", target_path)
        return
    _download_with_retry(
        source_urls,
        target_path,
        max_attempts,
        retry_seconds,
        timeout_seconds,
        trust_env,
        local_address,
    )


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
    model_fallback_urls = _parse_fallback_urls(os.getenv("PIPER_MODEL_FALLBACK_URLS"))
    config_fallback_urls = _parse_fallback_urls(os.getenv("PIPER_MODEL_CONFIG_FALLBACK_URLS"))
    trust_env = _is_true(os.getenv("PIPER_DOWNLOAD_TRUST_ENV"))
    local_address = os.getenv("PIPER_DOWNLOAD_LOCAL_ADDRESS", "0.0.0.0").strip() or None

    max_attempts = _get_int("PIPER_DOWNLOAD_MAX_ATTEMPTS", 5)
    retry_seconds = _get_int("PIPER_DOWNLOAD_RETRY_SECONDS", 2)
    timeout_seconds = _get_float("PIPER_DOWNLOAD_TIMEOUT_SECONDS", 120.0)

    model_urls = _dedupe_urls([model_url, *model_fallback_urls])
    config_urls = _dedupe_urls([model_config_url, *config_fallback_urls])

    LOGGER.info("Piper binary: %s", piper_bin)
    LOGGER.info("Model path: %s", model_path)
    LOGGER.info("Config path: %s", model_config_path)
    LOGGER.info("Piper download config: trust_env=%s local_address=%s", trust_env, local_address or "auto")

    _ensure_file(
        model_path,
        model_urls,
        max_attempts,
        retry_seconds,
        timeout_seconds,
        trust_env,
        local_address,
    )
    _ensure_file(
        model_config_path,
        config_urls,
        max_attempts,
        retry_seconds,
        timeout_seconds,
        trust_env,
        local_address,
    )

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
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Piper prewarm failed")
        _write_status(
            status_path,
            {
                "ok": False,
                "component": "piper",
                "message": f"piper prewarm failed: {exc}",
            },
        )
        raise SystemExit(1 if strict_mode else 0)
