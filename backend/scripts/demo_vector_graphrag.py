"""智考通 · 真实向量检索 + GraphRAG 演示。

运行：cd backend && python scripts/demo_vector_graphrag.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import numpy as np  # noqa: E402

from app.data.knowledge_graph import KG  # noqa: E402
from app.modules.rag.embeddings import BGEHttpEmbedder  # noqa: E402
from app.modules.rag.retriever import RETRIEVER  # noqa: E402
from app.modules.rag.reranker import BGEHttpReranker  # noqa: E402
from app.modules.rag.text_utils import minmax, tokenize  # noqa: E402
from scripts.fake_llm_server import build_mock_transport  # noqa: E402


def h(t):
    print("\n" + "═" * 72 + f"\n  {t}\n" + "═" * 72)


def main():
    R = RETRIEVER
    print("智考通 · 混合检索（BM25 + bge 向量 + GraphRAG）")
    h("① 当前后端")
    print(f"  嵌入：{R.embedder.backend} | 向量库：{R.store.backend}（真实余弦）| "
          f"chunk 数：{len(R.chunks)} | 已灌库：{R.store.count()}")
    print("  生产切换：.env 设 EMBEDDER_BACKEND=bge_http + VECTOR_STORE=milvus 即接真机")

    h("② 三路分解：BM25(关键词) vs Dense(向量) vs GraphRAG(图谱) → 融合")
    q = "求函数的单调区间与极值"
    bm = minmax(R.bm25.scores(tokenize(q)))
    de = minmax(R._dense_scores(q))
    gr = minmax(R.graph.score_chunks(q, [c.concept_ids for c in R.chunks]))
    from app.core.config import settings as st
    fused = st.retrieval_weight_bm25 * bm + st.retrieval_weight_dense * de + st.retrieval_weight_graph * gr
    print(f"  查询：「{q}」  权重 BM25/Dense/Graph = "
          f"{st.retrieval_weight_bm25}/{st.retrieval_weight_dense}/{st.retrieval_weight_graph}")
    print(f"    {'chunk':<22}{'BM25':<7}{'Dense':<7}{'Graph':<7}{'融合':<6}")
    for i in np.argsort(-fused)[:5]:
        c = R.chunks[i]
        print(f"    {c.ref_id+'('+c.kind[:4]+')':<22}{bm[i]:<7.2f}{de[i]:<7.2f}{gr[i]:<7.2f}{fused[i]:<6.2f}")

    h("③ GraphRAG：实体链接 → 带边权多跳扩散（含跨学科桥）")
    gq = "三角函数的图象与周期性"
    seeds = R.graph.link_entities(gq, k=3)
    print(f"  查询：「{gq}」")
    print("  实体链接（查询↔知识点嵌入 Top-3）：",
          [(KG.name_of(c), round(s, 2)) for c, s in seeds])
    rel = R.graph.expand(seeds, hops=2, decay=0.5)
    top = sorted(rel.items(), key=lambda kv: -kv[1])[:8]
    print("  多跳扩散后的相关知识点（按 relevance）：")
    for c, r in top:
        cross = " ⟵跨学科" if KG.subject_of(c) != "math" else ""
        print(f"    {KG.name_of(c):<18}{KG.subject_of(c):<10}{r:.2f}{cross}")

    h("④ 跨学科召回：一个查询同时召回数学与物理相关题/点")
    for c, s in R.retrieve("周期 振动 正弦", top_k=6):
        print(f"    [{KG.subject_of(c.concept_ids[0]) if c.concept_ids else '-':<8}] "
              f"{c.ref_id}（{c.kind}）融合分 {s:.2f}")

    h("⑤ 真实 bge 嵌入路径（假服务驱动生产客户端，真实 HTTP）")
    emb = BGEHttpEmbedder(http_client=httpx.Client(transport=build_mock_transport()))
    docs = ["单摆做简谐运动周期 T=2π√(L/g)", "等差数列前 n 项和公式", "光合作用暗反应在叶绿体基质"]
    dv = emb.embed(docs)
    qv = emb.embed(["简谐运动的周期"], is_query=True)[0]
    sims = dv @ qv
    print(f"  is_real 嵌入维度={dv.shape[1]}，查询余弦相似度：")
    for d, sim in sorted(zip(docs, sims), key=lambda t: -t[1]):
        print(f"    {sim:.3f}  {d}")

    h("⑥ bge-reranker 重排序（真实 HTTP）")
    rr = BGEHttpReranker(http_client=httpx.Client(transport=build_mock_transport()))
    cands = R.retrieve("电源 电动势 内阻 电流", top_k=5)
    for c, s in rr.rerank("电源 电动势 内阻 电流", cands, top_k=3):
        print(f"    {c.ref_id}（{c.kind}）重排分 {s:.3f}")

    print("\n" + "═" * 72)
    print("  演示结束。生产：EMBEDDER_BACKEND=bge_http / VECTOR_STORE=milvus / RERANKER_BACKEND=bge_http")
    print("═" * 72)


if __name__ == "__main__":
    main()
