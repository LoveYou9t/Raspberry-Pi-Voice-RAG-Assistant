from __future__ import annotations


class SentenceChunker:
    """Chunk token stream into sentence-sized text for TTS."""

    ENDINGS = {".", "!", "?", ";", "\n", "。", "！", "？", "；"}

    def __init__(self) -> None:
        self._buffer: list[str] = []

    def feed(self, token: str) -> list[str]:
        output: list[str] = []
        if not token:
            return output

        self._buffer.append(token)
        combined = "".join(self._buffer)

        start = 0
        for index, char in enumerate(combined):
            if char in self.ENDINGS:
                segment = combined[start : index + 1].strip()
                if segment:
                    output.append(segment)
                start = index + 1

        if start > 0:
            self._buffer = [combined[start:]]
        return output

    def flush(self) -> str:
        if not self._buffer:
            return ""
        tail = "".join(self._buffer).strip()
        self._buffer = []
        return tail
