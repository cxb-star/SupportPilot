"""Ingestion 入口：把 docs/*.txt 切块并写入 Chroma（支持本地 hash embedding 或 OpenAI 兼容 embedding）。"""
from pathlib import Path

from config import settings
from logging_config import get_ctx_logger
from rag.ingest import chunk_text
from rag.retriever import get_retriever

log = get_ctx_logger("ingest")


def main(docs_dir: str | Path | None = None) -> int:
    docs_dir = Path(docs_dir or settings.DOCS_DIR)
    if not docs_dir.exists():
        log.error("docs_dir_missing path=%s", docs_dir)
        return 0

    retriever = get_retriever()
    total = 0
    for path in sorted(docs_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(
            text,
            size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
            source=path.name,
            stem=path.stem,
        )
        items = [
            {
                "id": f"{path.stem}-{c.index}",
                "source": c.source,
                "content": c.content,
                "char_count": len(c.content),
            }
            for c in chunks
        ]
        total += retriever.add(items)
        log.info("ingested source=%s chunks=%d", path.name, len(items))

    log.info("ingest_done total_chunks=%d", total)
    print(f"ingest done: {total} chunks")
    return total


if __name__ == "__main__":
    main()
