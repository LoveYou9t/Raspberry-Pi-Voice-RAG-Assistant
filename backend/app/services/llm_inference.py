from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

import httpx

from app.services.sentence_stream import SentenceChunker

logger = logging.getLogger(__name__)


class OllamaLLMService:
    def __init__(
        self,
        host: str,
        model: str,
        num_ctx: int,
        temperature: float,
        top_k: int,
        keep_alive: str | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.top_k = top_k
        self.keep_alive = (keep_alive or "").strip()

    async def stream_tokens(
        self,
        prompt: str,
        interrupt_event,
    ) -> AsyncGenerator[str, None]:
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
                "top_k": self.top_k,
            },
        }
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if interrupt_event.is_set():
                            break
                        if not line:
                            continue

                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token

                        if data.get("done"):
                            break
        except Exception as exc:  # pragma: no cover
            logger.error("LLM stream failed: %s", exc)
            yield "I cannot reach the model service right now."

    async def warmup(
        self,
        prompt: str,
        timeout_seconds: float,
        retries: int,
        retry_delay_seconds: float,
    ) -> tuple[bool, str]:
        url = f"{self.host}/api/generate"
        attempts = max(1, retries + 1)
        last_message = "warmup not attempted"

        for attempt in range(1, attempts + 1):
            is_final_attempt = attempt == attempts
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 1,
                    "num_ctx": self.num_ctx,
                    "temperature": self.temperature,
                    "top_k": self.top_k,
                },
            }
            if self.keep_alive:
                payload["keep_alive"] = self.keep_alive

            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()

                if data.get("done", True):
                    message = f"warmup ok (attempt {attempt}/{attempts})"
                    logger.info("LLM warmup succeeded: %s", message)
                    return True, message

                last_message = f"warmup incomplete (attempt {attempt}/{attempts})"
                if is_final_attempt:
                    logger.warning("LLM warmup incomplete after retries: %s", last_message)
                else:
                    logger.info("LLM warmup retrying: %s", last_message)
            except Exception as exc:  # pragma: no cover
                last_message = f"warmup failed (attempt {attempt}/{attempts}): {exc}"
                if is_final_attempt:
                    logger.warning("LLM warmup failed after retries: %s", last_message)
                else:
                    logger.info("LLM warmup retrying: %s", last_message)

            if attempt < attempts:
                await asyncio.sleep(max(0.0, retry_delay_seconds))

        return False, last_message

    async def stream_sentences(self, prompt: str, interrupt_event) -> AsyncGenerator[str, None]:
        chunker = SentenceChunker()
        async for token in self.stream_tokens(prompt, interrupt_event):
            for sentence in chunker.feed(token):
                yield sentence

        tail = chunker.flush()
        if tail:
            yield tail
