"""真实向量检索 + GraphRAG 测试。

bge 嵌入与 reranker 用 MockTransport 在真实 HTTP 层验证；向量库用内存真实余弦；
GraphRAG 验证实体链接、带权多跳扩散与跨学科桥接。
"""
import httpx
import numpy as np

from app.modules.rag.embeddings import BGEHttpEmbedder, get_embedder
from app.modules.rag.graphrag import GraphRetriever
from app.modules.rag.reranker import BGEHttpReranker, HeuristicReranker
from app.modules.rag.retriever import RETRIEVER, Chunk
from app.modules.rag.text_utils import HashingEmbedder
from app.modules.rag.vectorstore import InMemoryVectorStore
from scripts.fake_llm_server import build_mock_transport


def mock_client():
    return httpx.Client(transport=build_mock_transport())


# ── 向量库（内存真实余弦）─────────────────────────────────────
def test_inmemory_vector_store_cosine_and_filter():
    vs = InMemoryVectorStore()
    v = HashingEmbedder(64).embed(["导数与极值", "光合作用", "电磁感应"])
    vs.upsert(["a", "b", "c"], v,
              [{"subject": "math"}, {"subject": "biology"}, {"subject": "physics"}])
    assert vs.count() == 3
    # 用 a 的向量查询 → a 最相近（余弦≈1）
    res = vs.search(v[0], top_k=3)
    assert res[0][0] == "a" and res[0][1] > 0.99
    # 标量过滤：只要 biology
    res_b = vs.search(v[0], top_k=3, where={"subject": "biology"})
    assert [r[0] for r in res_b] == ["b"]


# ── bge HTTP 嵌入（真实 HTTP）────────────────────────────────
def test_bge_http_embedder_over_http():
    emb = BGEHttpEmbedder(http_client=mock_client())
    v = emb.embed(["三角函数", "等差数列"])
    assert v.shape == (2, 256)
    assert abs(np.linalg.norm(v[0]) - 1.0) < 1e-6  # L2 归一化
    # 查询模式（加指令前缀）也应正常返回
    q = emb.embed(["单摆周期"], is_query=True)
    assert q.shape == (1, 256)


def test_get_embedder_defaults_to_mock():
    assert get_embedder().backend == "mock"  # 默认 embedder_backend=mock


# ── GraphRAG ────────────────────────────────────────────────
def test_graphrag_entity_linking_and_expansion():
    gr = GraphRetriever(HashingEmbedder(256))
    seeds = gr.link_entities("导数 单调区间 极值", k=3)
    assert any("DERIV" in c or "FUNC" in c for c, _ in seeds)  # 链接到导数/函数概念
    rel = gr.expand([("MATH_DERIV_EXTREME", 1.0)], hops=2, decay=0.5)
    # 扩散到其先修（导数与单调性）
    assert "MATH_DERIV_MONO" in rel and rel["MATH_DERIV_MONO"] > 0


def test_graphrag_cross_subject_bridge():
    gr = GraphRetriever(HashingEmbedder(256))
    rel = gr.expand([("MATH_TRIG_FUNC", 1.0)], hops=2, decay=0.5)
    assert "PHY_SHM" in rel and rel["PHY_SHM"] > 0  # 三角函数 → 简谐运动（跨学科桥，双向）
    rel2 = gr.expand([("BIO_PHOTOSYNTHESIS", 1.0)], hops=1, decay=0.5)
    assert "CHEM_EQUILIBRIUM" in rel2  # 光合作用 → 化学平衡


# ── 混合检索 ────────────────────────────────────────────────
def test_hybrid_retrieve_finds_relevant_and_subject_filter():
    top = RETRIEVER.retrieve("光合作用 暗反应 场所", top_k=3)
    assert any(c.ref_id == "B0003" for c, _ in top)  # 召回对应生物题
    # 学科过滤：只要物理
    phys = RETRIEVER.retrieve("周期 公式", top_k=5, subject="physics")
    assert phys and all(c.subject == "physics" for c, _ in phys)


# ── 重排序（真实 HTTP + 降级）────────────────────────────────
def _cands():
    return [(Chunk(id="1", text="单摆周期 T=2π√(L/g)", kind="problem", ref_id="P0006"), 0.5),
            (Chunk(id="2", text="光合作用暗反应在叶绿体基质", kind="problem", ref_id="B0003"), 0.5)]


def test_bge_http_reranker_over_http():
    rr = BGEHttpReranker(http_client=mock_client())
    out = rr.rerank("单摆 周期", _cands(), top_k=2)
    assert out[0][0].ref_id == "P0006"  # 与查询更相关者排前


def test_reranker_falls_back_on_error():
    t = httpx.MockTransport(lambda req: httpx.Response(500))
    rr = BGEHttpReranker(http_client=httpx.Client(transport=t))
    out = rr.rerank("单摆 周期", _cands(), top_k=2)
    assert len(out) == 2  # 降级到启发式仍可用
