"""检索器：Chroma 向量检索；支持 OpenAI 兼容 embedding，失败时退化为确定性 hash embedding。"""
import hashlib
from functools import lru_cache
from pathlib import Path

import chromadb

from config import settings
from logging_config import get_ctx_logger

log = get_ctx_logger("retriever")


def _hash_embedding(text: str, dim: int = 256) -> list[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    vec = []
    for i in range(dim):
        start = (i * 4) % len(seed)
        chunk = seed[start : start + 4]
        value = int.from_bytes(chunk, "big") / 0xFFFFFFFF
        vec.append((value - 0.5) * 2.0)
    return vec


class Retriever:
    def __init__(self):
        self.persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = settings.CHROMA_COLLECTION
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedding_func = None
        if settings.embedding_configured():
            from openai import OpenAI

            self.client_api = OpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                timeout=settings.EMBEDDING_TIMEOUT,
            )
            self.embedding_model = settings.EMBEDDING_MODEL
        log.info(
            "retriever_ready collection=%s embedding=%s",
            self.collection_name,
            "api" if settings.embedding_configured() else "hash",
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not settings.embedding_configured() or not getattr(self, "client_api", None):
            return [_hash_embedding(t) for t in texts]
        try:
            resp = self.client_api.embeddings.create(
                model=self.embedding_model, input=texts
            )
            return [item.embedding for item in resp.data]
        except Exception as exc:  # noqa: BLE001
            log.warning("embedding_failed fallback=hash error=%s", exc)
            return [_hash_embedding(t) for t in texts]

    def add(self, items: list[dict]) -> int:
        if not items:
            return 0
        texts = [item["content"] for item in items]
        embeddings = self._embed(texts)
        metadatas = [
            {
                "source": item.get("source", ""),
                "char_count": item.get("char_count", len(t)),
            }
            for item, t in zip(items, texts)
        ]
        self.collection.upsert(
            ids=[item["id"] for item in items],
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(items)

    def search(self, question: str, top_k: int = 5) -> list[dict]:
        count = self.collection.count()
        if count == 0:
            log.warning("search_empty_collection collection=%s", self.collection_name)
            return []
        embeddings = self._embed([question])
        results = self.collection.query(
            query_embeddings=embeddings,
            n_results=min(top_k, count),
        )
        docs = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i]
            score = max(0.0, min(1.0, 1.0 - distance / 2.0))
            docs.append(
                {
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "score": score,
                    "source": (results["metadatas"][0][i] or {}).get("source", ""),
                }
            )
        return docs


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()
