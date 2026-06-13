"""应用配置：全部由环境变量驱动，留空则用可运行的 Mock 后端。

设计原则：业务代码只读 `settings`，切换真实/Mock 后端无需改任何逻辑。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_timezone_offset_hours: int = 8  # 中国固定 UTC+8，无夏令时，避免依赖 tzdata

    # ── 合规：高考熔断窗口（含首尾日）─────────────────────────
    gaokao_blackout_start: date = date(2026, 6, 7)
    gaokao_blackout_end: date = date(2026, 6, 10)
    # 防沉迷
    daily_usage_limit_minutes: int = 180
    night_lock_start_hour: int = 23
    night_lock_end_hour: int = 6

    # ── 后端选择 ──────────────────────────────────────────
    parser_backend: str = "mock"
    embedder_backend: str = "mock"
    reranker_backend: str = "mock"
    llm_backend: str = "mock"

    # ── 真实 LLM（OpenAI 兼容：vLLM / DeepSeek / Qwen）──────────
    llm_base_url: str = "http://127.0.0.1:8001/v1"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen2-7B-Instruct"
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.2
    llm_json_mode: bool = True  # 结构化输出（作文评分等）走 JSON mode
    llm_cache_size: int = 256
    llm_health_check: bool = True  # 启动时探活，失败自动降级到 Mock

    # ── 真实 OCR/公式 ────────────────────────────────────
    ocr_endpoint: str = ""  # 通用 HTTP OCR 网关（统一契约）；留空用 Mock
    ocr_timeout_s: float = 20.0
    ocr_max_retries: int = 2
    baidu_formula_endpoint: str = ""
    baidu_api_key: str = ""
    baidu_secret_key: str = ""
    aliyun_edu_access_key: str = ""
    aliyun_edu_secret: str = ""

    # ── RAG 检索融合权重（BM25 / Dense / Graph）──────────────
    retrieval_weight_bm25: float = 0.3
    retrieval_weight_dense: float = 0.4
    retrieval_weight_graph: float = 0.3
    rerank_top_k: int = 10

    # ── 真实向量检索：bge 嵌入（mock | bge_http | bge_local）──────
    embed_base_url: str = "http://127.0.0.1:8001/v1"  # OpenAI/TEI 兼容 /embeddings
    embed_model: str = "bge-large-zh-v1.5"
    embed_dim: int = 256  # mock=256；bge-large-zh=1024，bge-m3=1024
    embed_timeout_s: float = 20.0
    embed_query_instruction: str = "为这个句子生成表示以用于检索相关文章："  # bge 非对称检索查询前缀
    embed_health_check: bool = True

    # ── 向量库（memory | milvus）────────────────────────────
    vector_store: str = "memory"  # memory=内存真实余弦；milvus=生产
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_collection: str = "zkt_chunks"
    milvus_metric: str = "COSINE"

    # ── 重排序服务（reranker_backend=bge_http 时）──────────────
    rerank_base_url: str = "http://127.0.0.1:8001"  # POST /rerank
    # GraphRAG 实体链接与扩散
    graphrag_link_top_k: int = 3
    graphrag_hops: int = 2
    graphrag_decay: float = 0.5

    @property
    def tz(self) -> timezone:
        return timezone(timedelta(hours=self.app_timezone_offset_hours))

    def now(self) -> datetime:
        """当前本地时间（Asia/Shanghai 等效，UTC+8）。"""
        return datetime.now(self.tz)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
