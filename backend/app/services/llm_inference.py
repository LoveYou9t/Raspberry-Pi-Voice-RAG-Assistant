from __future__ import annotations

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
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.top_k = top_k

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

    async def stream_sentences(self, prompt: str, interrupt_event) -> AsyncGenerator[str, None]:
        chunker = SentenceChunker()
        async for token in self.stream_tokens(prompt, interrupt_event):
            for sentence in chunker.feed(token):
                yield sentence

        tail = chunker.flush()
        if tail:
            yield tail
