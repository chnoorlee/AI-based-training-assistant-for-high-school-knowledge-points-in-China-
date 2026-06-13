# 智考通 · 基于认知诊断的高考自适应备考助手（数学 / 物理 / 化学 / 生物）

> **合规声明（红线）**：本项目**不提供任何形式的"押题/原题预测/命中率"功能**。核心定位是
> **「基于纳米级认知诊断的个性化提分工具」**——帮助学生用最少时间补齐知识短板、提升解题能力。
> 原文件夹名 `高考AI押题助手` 仅为历史目录名，对外产品名、代码与文档统一为 **「智考通 / ZhiKaoTong」**。

本仓库是 **第一阶段（Month 1-4）数学学科 MVP** 的可运行端到端骨架，打通核心链路：

```
①多模态解析(OCR/公式)  →  ②混合RAG解题(强制苏格拉底引导)  →  ③认知诊断(NeuralCD + 知识追踪)  →  ④变式题自适应推荐
                                    ▲
                    全链路合规闸门：高考熔断 + 防沉迷 + 监护
```

## 为什么"现在就能跑"

为了让你 **不装 NebulaGraph / Milvus / 大模型权重就能验证整条链路**，本骨架做了工程取舍：

| 能力 | MVP 实现（可跑） | 生产替换点（已留接口） |
|---|---|---|
| OCR / 公式识别 | `MockEduParser`（规则解析 + 内置样例） | **`HttpEduParser` ✅已落地**（统一 HTTP 网关，超时/重试/降级）→ 百度 PP-FormulaNet / 阿里云 |
| 向量检索 | `HashingEmbedder` + `InMemoryVectorStore`（**真实余弦**，零依赖） | **`BGEHttpEmbedder` ✅ + `MilvusVectorStore` ✅**（bge-m3/bge-large + Milvus）|
| GraphRAG | ✅ 实体链接 + 带权多跳扩散（跨学科桥）| 同图谱，可换 NebulaGraph 后端 |
| 重排序 | `HeuristicReranker`（特征打分） | **`BGEHttpReranker` ✅** → bge-reranker-large |
| 大模型解题 | `MockSolverLLM`（基于题库的确定性引导） | **`OpenAICompatibleClient` ✅已落地**（超时/重试/JSON/缓存/探活降级，苏格拉底门控+幻觉护栏）→ DeepSeek-R1 / Qwen2（vLLM） |
| 知识图谱 | 内存图（真实数学知识点 + 先修边 + 跨学科边） | NebulaGraph |
| 认知诊断 | NeuralCD（NumPy）+ BKT（默认回退路径） | **NeuralCD+DKT 联合训练（PyTorch，已落地）**：装 torch + 跑 `train_diagnosis.py`，引擎自动升级 |

> 所有 Mock 都实现了与生产同名的接口（`EduParser` / `Embedder` / `Reranker` / `LLMClient`），
> 配好 `.env` 里的真实服务地址即可热插拔，**业务代码零改动**。

## 快速开始

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows PowerShell
pip install -r requirements.txt

# 方式一：一键端到端演示（不需要起服务，进程内跑完整链路）
python scripts/demo.py
python scripts/demo_variant.py    # 变式题生成（参数化+情境+质检+审核+苏格拉底回流）
python scripts/demo_grading.py    # 主观题批改（作文 3×4 维 + 文综采分点）
python scripts/demo_mlops.py      # MLOps（监控告警 + A/B 灰度 + PSI 漂移）
python scripts/demo_real.py       # 真实 OCR/LLM 接入（生产客户端，假服务驱动，无需 key）
python scripts/demo_review.py      # 错题本智能复习排程（SM-2 间隔重复 + 遗忘曲线）
python scripts/demo_multisubject.py # 多学科（物理/化学/生物 + 跨学科关联 + 学科切片诊断）
python scripts/demo_vector_graphrag.py # 真实向量检索（bge）+ GraphRAG（实体链接+多跳扩散+跨学科桥）
python scripts/demo_planner.py     # ★AI 提分规划师（性价比排序 + 倒计时每日计划 + 预计提分）
python scripts/demo_mock_feedback.py # 模考估分 + 真实模考反馈闭环（校准 + 识别应试丢分 + 规划重排）
python scripts/demo_execution.py   # ★应试丢分细分到题型 + 限时训练（选择手滑/压轴抢分 → 排进每日首项）

# 方式二：启动 API 服务
uvicorn app.main:app --reload
# 打开 http://127.0.0.1:8000/docs 交互式调试

# 跑测试
pytest -q

# 方式三：把认知诊断升级为 PyTorch 版 NeuralCD + DKT 联合训练
pip install torch --index-url https://download.pytorch.org/whl/cpu   # 若未装
python scripts/train_diagnosis.py    # 联合训练→存 artifacts/diagnosis_joint.pt
# 之后重启服务/重跑 demo，DiagnosisEngine 自动切换到联合模型（业务代码零改动）

# 方式四：真实日志驱动的训练流水线 + 增量更新调度
python scripts/train_pipeline.py --demo     # 两天流量→全量v1→增量v2→门控晋升→注册表→热加载
python scripts/train_pipeline.py --once --incremental   # 生产：从日志增量训练一次（cron/K8s 调度此命令）
```

> **诊断双路径**：装了 torch 且存在 checkpoint → 用 **NeuralCD+DKT 联合模型**；
> 否则自动回退 **NumPy NeuralCD + BKT**。两条路径输出同一份 `DiagnosisReport`，全部功能可用。

## 目录结构

```
backend/
├─ app/
│  ├─ main.py                    # FastAPI 入口
│  ├─ core/
│  │  ├─ config.py               # 配置（环境变量驱动，可切换真实/Mock 后端）
│  │  └─ compliance.py           # ★ 合规核心：高考熔断 / 防沉迷 / 监护
│  ├─ schemas.py                 # 全量 Pydantic 数据模型（统一 JSON 契约）
│  ├─ data/
│  │  ├─ seed_data.py            # 数学知识点 + 高考风格种子题
│  │  ├─ seed_data_science.py    # 物理/化学/生物 概念+题+跨学科边
│  │  ├─ knowledge_graph.py      # 统一知识图谱（含学科切片）
│  │  └─ problem_bank.py         # 题库 + Q 矩阵（by_subject）
│  ├─ modules/
│  │  ├─ parsing.py              # ① 多模态解析（接口 + Mock）
│  │  ├─ rag/
│  │  │  ├─ retriever.py         # ② BM25 + Dense(向量库) + GraphRAG 融合
│  │  │  ├─ embeddings.py        #    bge 嵌入（HTTP/本地/哈希回退）
│  │  │  ├─ vectorstore.py       #    向量库（内存真实余弦 / Milvus）
│  │  │  ├─ graphrag.py          #    实体链接 + 带权多跳图扩散
│  │  │  ├─ reranker.py          #    重排序（启发式 / bge-reranker HTTP）
│  │  │  ├─ llm.py               #    LLM 接口 + Mock + OpenAI 兼容（生产级）
│  │  │  ├─ guards.py            #    内容安全 + 知识点幻觉核验
│  │  │  └─ solver.py            #    解题编排：苏格拉底引导 + 幻觉校验
│  │  ├─ diagnosis/
│  │  │  ├─ neural_cd.py         # ③ NeuralCD（NumPy，回退路径）
│  │  │  ├─ knowledge_tracing.py #    BKT 知识追踪（回退路径）
│  │  │  ├─ torch_models.py      #    NeuralCDNet(正权重MLP) + DKTNet(LSTM)
│  │  │  ├─ synthetic.py         #    带真值的合成作答日志
│  │  │  ├─ joint_trainer.py     #    联合训练 + AUC/ACC/Oracle 评估
│  │  │  ├─ torch_backend.py     #    torch 服务推理（在线θ + DKT序列）+ 热加载
│  │  │  ├─ dataset.py           #    数据接入：日志仓储 + 训练集构造
│  │  │  ├─ pipeline.py          #    训练流水线：增量/热启动/门控/原子切换/注册表
│  │  │  ├─ scheduler.py         #    增量更新调度（定时按需触发）
│  │  │  ├─ traffic_sim.py       #    演示/测试用作答日志回填
│  │  │  └─ engine.py            #    自动检测 torch；混合诊断 + 冷启动 + 雷达图 + 热加载
│  │  ├─ recommend.py            # ④ ZPD + 遗忘曲线 + 70/20/10 推荐
│  │  ├─ variant/                # ④ 变式题生成
│  │  │  ├─ templates.py         #    6 参数化模板 + 符号求解器（保证数学正确）
│  │  │  ├─ scenarios.py         #    10 大类情境库
│  │  │  ├─ quality.py           #    规则/难度/去重/版权/安全 质检
│  │  │  ├─ review.py            #    人工审核状态机
│  │  │  └─ generator.py         #    生成编排 + 批内去重
│  │  ├─ grading/                # ⑤ 主观题批改
│  │  │  ├─ essay.py             #    作文 3×4 维细则评分 + 校准
│  │  │  └─ subjective.py        #    文综/理综采分点匹配 + 逻辑评价
│  │  ├─ mlops/                  # Ops 监控/灰度/漂移
│  │  │  ├─ monitoring.py        #    埋点 + Prometheus + 告警
│  │  │  ├─ ab.py                #    A/B 灰度（晋升/回滚决策）
│  │  │  └─ drift.py             #    PSI 特征/标签漂移检测
│  │  └─ review/                 # 错题本智能复习排程
│  │     ├─ scheduler.py         #    SM-2 间隔重复 + 遗忘曲线 + 掌握度
│  │     └─ book.py              #    每日队列/统计/预测 + 接入作答
│  ├─ services/store.py          # 内存数据存储（用户 / 作答 / 用量）
│  └─ api/routers.py             # 路由层（全部走合规闸门）
├─ scripts/
│  ├─ demo.py                    # 核心链路端到端演示
│  ├─ demo_variant.py            # 变式题生成端到端演示
│  ├─ demo_grading.py            # 主观题批改端到端演示
│  ├─ demo_mlops.py              # MLOps（监控/灰度/漂移）端到端演示
│  ├─ demo_real.py               # 真实 OCR/LLM 接入演示（自由输入解题+作文批改）
│  ├─ demo_review.py             # 错题本智能复习排程演示
│  ├─ demo_multisubject.py       # 多学科（物理/化学/生物）演示
│  ├─ demo_vector_graphrag.py    # 真实向量检索 + GraphRAG 演示
│  ├─ demo_execution.py          # 应试丢分细分到题型 + 限时训练演示
│  ├─ fake_llm_server.py         # 契约一致的假 LLM/OCR/嵌入/重排序 服务（联调+测试）
│  ├─ train_diagnosis.py         # NeuralCD+DKT 单次联合训练（合成数据）
│  └─ train_pipeline.py          # 真实日志训练流水线 + 增量更新调度
├─ artifacts/                    # 训练产物：diagnosis_joint.pt + checkpoints/ + registry.json
├─ tests/                        # 合规 / 诊断 / 苏格拉底 / 推荐 单测
├─ requirements.txt
└─ pyproject.toml

docs/
├─ PRD-数学MVP.md                # 产品需求文档（MVP 范围）
├─ 技术架构-数学MVP.md            # 技术架构设计
└─ 合规设计.md                    # 全链路合规体系（双备案/熔断/防沉迷/数据安全）

frontend/
├─ admin-vue/                    # 管理后台（Vue3 + Vite）— 教师/运营端，浏览器可跑
└─ student-rn/                   # 学生端（React Native / Expo）
```

## 前端（frontend/）

对接同一 FastAPI（已开 CORS）。详见 [frontend/README.md](frontend/README.md)。

```bash
# 1) 先起后端：cd backend && uvicorn app.main:app --port 8000
# 2) 管理后台（Vue3，浏览器）
cd frontend/admin-vue && npm install && npm run dev      # → http://localhost:5173
# 3) 学生端（React Native / Expo）
cd frontend/student-rn && npm install && npx expo start  # 按 w 开网页版 / 扫码用 Expo Go
```
- **管理后台**：概览（监控/灰度/漂移）· 学情诊断（跨学科雷达 + 推荐）· 变式题审核 · 错题复习。
- **学生端**：诊断 · 苏格拉底解题（三级门控）· 推荐 · 错题本（SM-2 复习）。

## 已落地的关键合规与教育约束

- **绝不直接给答案**：`/solve` 首次响应只返回 3 个苏格拉底式引导问题；最终答案被门控在「引导步骤」之后，且必须附完整思维链。
- **高考熔断**：6 月 7–10 日（可配置，Asia/Shanghai）自动关闭解析/解题/作文，仅保留错题本与知识点复习。
- **防沉迷**：单日 ≤3 小时、23:00–06:00 锁定，按用户累计用量。
- **幻觉抑制**：解题输出的知识点二次核验，未在知识图谱中命中的结论标记为「待人工复核」。
- **数据最小化**：只存学习相关数据（作答、用量、掌握度），不采集无关个人信息。

详见 [docs/合规设计.md](docs/合规设计.md)。
