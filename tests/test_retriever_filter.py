"""检索过滤测试：验证 policy 文档优先召回，task3 等调试文档被排除。"""
import pytest
import chromadb
from pathlib import Path

from rag.ingest_main import main as ingest_main
from rag.retriever import get_retriever


@pytest.fixture(scope="session", autouse=True)
def _ensure_chroma_has_policy_data():
    db_path = Path("data/chroma")
    if db_path.exists() and db_path.joinpath("chroma.sqlite3").exists():
        client = chromadb.PersistentClient(path=str(db_path))
        col = client.get_collection("knowledge_base")
        sample = col.get(limit=1)
        if sample["metadatas"] and sample["metadatas"][0].get("doc_type"):
            return
    ingest_main()


def test_search_excludes_debug_docs():
    retriever = get_retriever()
    docs = retriever.search("双11满减规则是什么", top_k=4)
    sources = [d["source"] for d in docs]
    assert not any("task3" in s for s in sources), f"debug 文档污染: {sources}"


def test_search_includes_policy_docs():
    retriever = get_retriever()
    docs = retriever.search("双11满减规则是什么", top_k=4)
    sources = [d["source"] for d in docs]
    assert any("promo" in s or "compensation" in s for s in sources), f"未召回政策: {sources}"


def test_search_refund_returns_refund_policy():
    retriever = get_retriever()
    docs = retriever.search("订单12345能退款吗买了3天", top_k=4)
    sources = [d["source"] for d in docs]
    assert any("refund" in s for s in sources), f"未召回退款政策: {sources}"


def test_where_filter_fallback_on_error(monkeypatch):
    """where 过滤失败时回退到无过滤检索，不抛异常。"""
    retriever = get_retriever()
    call_count = [0]
    orig_query = retriever.collection.query
    dim = retriever.collection.metadata.get("dimension") or 256

    def conditional_query(**kw):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("where filter error")
        return orig_query(query_embeddings=[[0.1] * dim], n_results=4)

    monkeypatch.setattr(retriever.collection, "query", conditional_query)
    result = retriever.search("随便问什么", top_k=4)
    assert isinstance(result, list)
    assert call_count[0] == 2
