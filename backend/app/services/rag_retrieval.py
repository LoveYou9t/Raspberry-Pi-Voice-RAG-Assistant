# // AI辅助生成：ChatGPT-5.3 Codex, 2025-11-03
from __future__ import annotations

import importlib
import logging
from pathlib import Path

from app.services.vectorizer import text_to_vector

logger = logging.getLogger(__name__)


class RAGService:
    """Retrieve context from LanceDB if available, else fallback to file scoring."""

    def __init__(
        self,
        knowledge_dir: str,
        lancedb_dir: str,
        table_name: str,
        vector_dim: int,
    ) -> None:
        self.knowledge_path = Path(knowledge_dir)
        self.vector_dim = vector_dim
        self.mode = "file"
        self.table = None

        try:
            lancedb = importlib.import_module("lancedb")

            db = lancedb.connect(lancedb_dir)
            if table_name in db.table_names():
                self.table = db.open_table(table_name)
                self.mode = "lancedb"
                logger.info("RAG initialized with LanceDB table: %s", table_name)
            else:
                logger.warning("LanceDB table %s not found, using file fallback.", table_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("LanceDB unavailable, using file fallback: %s", exc)

    def retrieve_context(self, query: str, top_k: int) -> list[str]:
        query = query.strip()
        if not query:
            return []

        if self.mode == "lancedb" and self.table is not None:
            try:
                vector = text_to_vector(query, self.vector_dim).tolist()
                rows = self.table.search(vector).limit(top_k).to_list()
                return [row.get("text", "") for row in rows if row.get("text")]
            except Exception as exc:  # pragma: no cover
                logger.warning("LanceDB search failed, fallback to file mode: %s", exc)

        return self._file_retrieve(query, top_k)

    def _file_retrieve(self, query: str, top_k: int) -> list[str]:
        if not self.knowledge_path.exists():
            return []

        terms = [term for term in query.lower().split() if term]
        scored: list[tuple[int, str]] = []

        for path in self.knowledge_path.glob("**/*"):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            body = text.strip()
            if not body:
                continue

            score = 0
            lower = body.lower()
            for term in terms:
                score += lower.count(term)

            if score == 0 and any(ch in query for ch in body[:200]):
                score = 1

            if score > 0:
                scored.append((score, body[:800]))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    @staticmethod
    def build_prompt(user_text: str, contexts: list[str]) -> str:
        if not contexts:
            return (
                "You are a local voice assistant. "
                "Answer clearly and briefly.\n\n"
                f"User: {user_text}"
            )

        joined = "\n\n---\n\n".join(contexts)
        return (
            "You are a local RAG voice assistant. "
            "Use provided context first; if context is insufficient, say so clearly.\n\n"
            f"Context:\n{joined}\n\n"
            f"User: {user_text}"
        )
