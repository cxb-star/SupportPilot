"""文档切块与入库：段落感知 + 固定长度兜底，切块结果可直接写入 Chroma。"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    index: int
    content: str
    source: str


def _split_by_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []
    merged = []
    buf = ""
    for para in paragraphs:
        if not buf:
            buf = para
            continue
        if len(buf) + len(para) + 1 > 900:
            merged.append(buf)
            buf = para
        else:
            buf = f"{buf}\n{para}"
    if buf:
        merged.append(buf)
    return merged


def _split_fixed(text: str, size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


def chunk_text(
    text: str,
    size: int = 300,
    overlap: int = 60,
    source: str = "",
    stem: str = "",
) -> list[Chunk]:
    segments = _split_by_paragraphs(text) or [text.strip()]
    chunks: list[Chunk] = []
    idx = 0
    for seg in segments:
        pieces = _split_fixed(seg, size, overlap)
        for piece in pieces:
            chunks.append(Chunk(index=idx, content=piece, source=source or stem or "unknown"))
            idx += 1
    return chunks


def ingest_documents(docs_dir: str | Path) -> list[dict]:
    docs_dir = Path(docs_dir)
    items = []
    for path in sorted(docs_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text, source=path.name, stem=path.stem)
        for chunk in chunks:
            items.append(
                {
                    "id": f"{path.stem}-{chunk.index}",
                    "source": chunk.source,
                    "content": chunk.content,
                    "char_count": len(chunk.content),
                }
            )
    return items
