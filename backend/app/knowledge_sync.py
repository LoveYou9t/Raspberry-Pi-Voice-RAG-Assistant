from __future__ import annotations

import hashlib
import importlib
import json
import logging
import re
from pathlib import Path

from app.config import settings
from app.services.vectorizer import text_to_vector

logger = logging.getLogger(__name__)

STATE_FILE = ".knowledge_state.json"
HEADER_SPLIT_PATTERN = re.compile(r"\n(?=#{1,6}\s)")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def split_markdown(text: str) -> list[str]:
    parts = [part.strip() for part in HEADER_SPLIT_PATTERN.split(text) if part.strip()]
    chunks: list[str] = []

    for part in parts:
        if len(part) <= 900:
            chunks.append(part)
            continue

        start = 0
        while start < len(part):
            chunks.append(part[start : start + 900])
            start += 700

    return chunks


def load_state(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state_path: Path, state: dict[str, str]) -> None:
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_files(knowledge_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in knowledge_dir.glob("**/*")
        if path.suffix.lower() in {".md", ".txt"} and path.is_file()
    )


def ensure_table(db):
    pa = importlib.import_module("pyarrow")
    table_name = settings.lancedb_table
    if table_name in db.table_names():
        return db.open_table(table_name)

    schema = pa.schema(
        [
            pa.field("id", pa.string(), nullable=False),
            pa.field("source", pa.string(), nullable=False),
            pa.field("text", pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), settings.vector_dim), nullable=False),
        ]
    )
    return db.create_table(table_name, schema=schema, data=[])


def remove_sources(table, sources: list[str]) -> None:
    if not sources:
        return
    escaped = [source.replace("'", "''") for source in sources]
    if len(escaped) == 1:
        where_clause = f"source = '{escaped[0]}'"
    else:
        values = ", ".join(f"'{item}'" for item in escaped)
        where_clause = f"source IN ({values})"
    table.delete(where_clause)


def build_rows(paths: list[Path], knowledge_root: Path) -> list[dict]:
    rows: list[dict] = []

    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        relative_source = str(path.relative_to(knowledge_root)).replace("\\", "/")

        for index, chunk in enumerate(split_markdown(text)):
            chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:12]
            row_id = f"{relative_source}:{index}:{chunk_hash}"
            vector = text_to_vector(chunk, settings.vector_dim).tolist()
            rows.append(
                {
                    "id": row_id,
                    "source": relative_source,
                    "text": chunk,
                    "vector": vector,
                }
            )

    return rows


def sync_once() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    try:
        lancedb = importlib.import_module("lancedb")
    except Exception as exc:  # pragma: no cover
        logger.error("LanceDB import failed: %s", exc)
        return

    knowledge_dir = Path(settings.knowledge_dir)
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    state_path = Path(settings.lancedb_dir) / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)

    old_state = load_state(state_path)
    files = collect_files(knowledge_dir)

    new_state = {str(path.relative_to(knowledge_dir)).replace("\\", "/"): file_sha256(path) for path in files}

    changed = [
        path
        for path in files
        if old_state.get(str(path.relative_to(knowledge_dir)).replace("\\", "/"))
        != new_state[str(path.relative_to(knowledge_dir)).replace("\\", "/")]
    ]
    deleted_sources = [source for source in old_state if source not in new_state]

    db = lancedb.connect(settings.lancedb_dir)
    table = ensure_table(db)

    remove_sources(table, deleted_sources)
    remove_sources(
        table,
        [str(path.relative_to(knowledge_dir)).replace("\\", "/") for path in changed],
    )

    rows = build_rows(changed, knowledge_dir)
    if rows:
        table.add(rows)

    if hasattr(table, "optimize"):
        try:
            table.optimize()
        except Exception:
            logger.info("Table optimize skipped")

    save_state(state_path, new_state)
    logger.info(
        "Knowledge sync complete: changed=%d deleted=%d indexed_rows=%d",
        len(changed),
        len(deleted_sources),
        len(rows),
    )


if __name__ == "__main__":
    sync_once()
