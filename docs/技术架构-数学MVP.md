# 智考通 · 技术架构设计（数学学科 MVP）

## 1. 总体数据流

```
                 ┌──────────────────────────────────────────────┐
   学生上传题/作答 │             合规闸门 compliance               │  ← 高考熔断 / 防沉迷
                 │     (每个"做题"请求先过 enforce(feature))     │
                 └───────────────────┬──────────────────────────┘
                                     ▼
  ① 解析 parsing ──► ParsedProblem(JSON, 含手写判错)
                                     │
                                     ▼
  ② 解题 solver ──► 检索(BM25+Dense+Graph) → 重排 → LLM
       │            └─ 三级门控：HINT(3问) → GUIDED(分步) → FULL(完整链+答案)
       │            └─ 幻觉抑制：知识点对照图谱核验
       ▼
   作答记录 store ──────────────────────────────────────────┐
                                     │                       │
                                     ▼                       ▼
  ③ 诊断 diagnosis(NeuralCD + BKT) ──► DiagnosisReport   ④ 推荐 recommend(ZPD+遗忘曲线+70/20/10)
                                     │                       │
                                     └────► 雷达图/薄弱点 ────┘──► 个性化习题列表
```

## 2. 模块 → 文件映射

| 层 | 模块 | 文件 | 关键实现 |
|---|---|---|---|
| 入口 | API | [main.py](../backend/app/main.py) / [api/routers.py](../backend/app/api/routers.py) | FastAPI，全部走合规闸门 |
| 核心 | 配置 | [core/config.py](../backend/app/core/config.py) | 环境变量驱动，mock/real 切换 |
| 核心 | 合规 | [core/compliance.py](../backend/app/core/compliance.py) | 熔断 + 防沉迷（纯函数，可测）|
| 契约 | Schemas | [schemas.py](../backend/app/schemas.py) | 统一 JSON 数据模型 |
| 数据 | 知识图谱 | [data/knowledge_graph.py](../backend/app/data/knowledge_graph.py) | 内存图（→NebulaGraph）|
| 数据 | 题库/Q阵 | [data/problem_bank.py](../backend/app/data/problem_bank.py) | Q 矩阵构建 |
| 数据 | 种子 | [data/seed_data.py](../backend/app/data/seed_data.py) | 数学 23 知识点 + 14 题 |
| 数据 | 理综种子 | [data/seed_data_science.py](../backend/app/data/seed_data_science.py) | 物理/化学/生物概念+题+跨学科边 |
| ① | 解析 | [modules/parsing.py](../backend/app/modules/parsing.py) | OCR/公式接口 + Mock + 手写判错 |
| ② | 检索 | [modules/rag/retriever.py](../backend/app/modules/rag/retriever.py) | BM25+Dense(向量库)+GraphRAG 融合 |
| ② | 嵌入 | [modules/rag/embeddings.py](../backend/app/modules/rag/embeddings.py) | bge HTTP / 本地 / 哈希回退 |
| ② | 向量库 | [modules/rag/vectorstore.py](../backend/app/modules/rag/vectorstore.py) | 内存真实余弦 / Milvus |
| ② | GraphRAG | [modules/rag/graphrag.py](../backend/app/modules/rag/graphrag.py) | 实体链接+带权多跳扩散 |
| ② | 重排 | [modules/rag/reranker.py](../backend/app/modules/rag/reranker.py) | 启发式 / bge-reranker HTTP |
| ② | LLM | [modules/rag/llm.py](../backend/app/modules/rag/llm.py) | Mock + OpenAI 兼容（vLLM）|
| ② | 解题编排 | [modules/rag/solver.py](../backend/app/modules/rag/solver.py) | 三级门控 + 幻觉抑制 |
| ③ | NeuralCD(np) | [modules/diagnosis/neural_cd.py](../backend/app/modules/diagnosis/neural_cd.py) | NumPy 真实梯度下降（回退路径）|
| ③ | 知识追踪 | [modules/diagnosis/knowledge_tracing.py](../backend/app/modules/diagnosis/knowledge_tracing.py) | BKT（回退路径）|
| ③ | torch 模型 | [modules/diagnosis/torch_models.py](../backend/app/modules/diagnosis/torch_models.py) | NeuralCDNet(正权重MLP) + DKTNet(LSTM) |
| ③ | 联合训练 | [modules/diagnosis/joint_trainer.py](../backend/app/modules/diagnosis/joint_trainer.py) | 联合损失 + AUC/ACC/Oracle 评估 |
| ③ | 合成数据 | [modules/diagnosis/synthetic.py](../backend/app/modules/diagnosis/synthetic.py) | 带真值的作答日志生成 |
| ③ | torch 服务 | [modules/diagnosis/torch_backend.py](../backend/app/modules/diagnosis/torch_backend.py) | 在线 θ 估计 + DKT 序列推理 |
| ③ | 诊断引擎 | [modules/diagnosis/engine.py](../backend/app/modules/diagnosis/engine.py) | 自动检测 torch；混合 + 雷达 + 归因 + 热加载 |
| ③ | 数据接入 | [modules/diagnosis/dataset.py](../backend/app/modules/diagnosis/dataset.py) | 日志仓储接口 + 训练集构造 |
| ③ | 训练流水线 | [modules/diagnosis/pipeline.py](../backend/app/modules/diagnosis/pipeline.py) | 增量/热启动/门控/原子切换/注册表 |
| ③ | 更新调度 | [modules/diagnosis/scheduler.py](../backend/app/modules/diagnosis/scheduler.py) | 定时按需触发（cron/K8s 说明）|
| ③ | 流量模拟 | [modules/diagnosis/traffic_sim.py](../backend/app/modules/diagnosis/traffic_sim.py) | 演示/测试用作答日志回填 |
| ④ | 推荐 | [modules/recommend.py](../backend/app/modules/recommend.py) | ZPD + 遗忘曲线 + 配比 |
| ④ | 变式模板 | [modules/variant/templates.py](../backend/app/modules/variant/templates.py) | 6 参数化模板 + 符号求解器 |
| ④ | 情境库 | [modules/variant/scenarios.py](../backend/app/modules/variant/scenarios.py) | 10 大类应用情境 |
| ④ | 变式质检 | [modules/variant/quality.py](../backend/app/modules/variant/quality.py) | 规则/难度/去重/版权/安全 |
| ④ | 变式审核 | [modules/variant/review.py](../backend/app/modules/variant/review.py) | 人工审核状态机 |
| ④ | 变式生成 | [modules/variant/generator.py](../backend/app/modules/variant/generator.py) | 编排 + 批内去重 |
| 规划 | 提分规划师 | [modules/planner/planner.py](../backend/app/modules/planner/planner.py) | ROI 最优化 + 倒计时/熔断编排 |
| 规划 | 考点蓝图 | [data/exam_blueprint.py](../backend/app/data/exam_blueprint.py) | 各模块高考分值权重 |
| 估分 | 模考预测 | [modules/exam/predictor.py](../backend/app/modules/exam/predictor.py) | 掌握度×分值→各科/总分+校准 |
| 估分 | 模考校准 | [modules/exam/mock_store.py](../backend/app/modules/exam/mock_store.py) | 真实模考拟合偏置 + 趋势 |
| 估分 | 反馈信号 | [modules/exam/feedback.py](../backend/app/modules/exam/feedback.py) | 应试丢分/退步→各科加权 |
| 估分 | 卷面结构 | [data/exam_paper.py](../backend/app/data/exam_paper.py) | 各科分题型区块(选择/填空/解答·易中难压轴) |
| 估分 | 题型丢分 | [modules/exam/sections.py](../backend/app/modules/exam/sections.py) | 按掌握度估各区块应得→定位丢分→开限时训练 |
| 错题 | 复习排程 | [modules/review/scheduler.py](../backend/app/modules/review/scheduler.py) | SM-2 + 遗忘曲线 + 掌握度调制 |
| 错题 | 复习管理 | [modules/review/book.py](../backend/app/modules/review/book.py) | 每日队列/统计/预测 + 接入作答 |
| ⑤ | 作文批改 | [modules/grading/essay.py](../backend/app/modules/grading/essay.py) | 3×4 维细则评分 + 校准 |
| ⑤ | 主观题批改 | [modules/grading/subjective.py](../backend/app/modules/grading/subjective.py) | 采分点匹配 + 逻辑评价 |
| Ops | 监控告警 | [modules/mlops/monitoring.py](../backend/app/modules/mlops/monitoring.py) | 埋点 + Prometheus + 告警 |
| Ops | A/B 灰度 | [modules/mlops/ab.py](../backend/app/modules/mlops/ab.py) | 稳定分桶 + 晋升/回滚决策 |
| Ops | 漂移检测 | [modules/mlops/drift.py](../backend/app/modules/mlops/drift.py) | PSI 特征/标签漂移 |
| 服务 | 存储 | [services/store.py](../backend/app/services/store.py) | 内存（→MySQL/Mongo）|

## 3. 关键算法

### 3.1 混合检索（RAG）
- 分块：题目级（结构感知）+ 知识点级（语义）。
- 三路：BM25（关键词，Okapi）/ Dense（向量余弦）/ Graph（图谱邻居命中）。
- 融合权重 0.3 / 0.4 / 0.3（`settings`，PRD 2.1），各路 min-max 归一后线性加权 → 重排取 Top-K。
- 生产替换：Embedder→bge-m3、向量库→Milvus、图→NebulaGraph、Reranker→bge-reranker-large。

### 3.2 NeuralCD（认知诊断核心）
- 学生在知识点 k 的掌握度 `A_sk = σ(θ_sk) ∈ (0,1)`，**直接喂雷达图，天然可解释**。
- 题目难度 `B_ik`、区分度 `D_i` 由 IRT 标定（种子题已给）。
- 交互：`P(答对) = σ(γ · Σ_k Q_ik·D_i·(A_sk − B_ik))`；掌握高于难度 → 答对概率高。
- 训练（服务期）：固定题目参数，对该生 θ 做梯度下降 MAP 估计，几条作答即收敛，支持冷启动/增量。
- 生产升级：原文"正权重 MLP 交互层" + θ/B/D 联合训练（PyTorch），接口不变。

### 3.3 BKT 知识追踪
- 每知识点 4 参数（init/transit/slip/guess），按作答序列在线更新 `P(已掌握)` 并预测下一题。
- 与 NeuralCD 加权融合（0.6/0.4）：前者给"多点静态画像"，后者给"动态趋势"。
- 这是**无 torch 时的轻量回退路径**；torch 可用时升级为 DKT-LSTM 联合训练（见 3.5）。

### 3.5 PyTorch 版 NeuralCD + DKT 联合训练（已落地）
> 引擎在启动时自动检测 torch 与 checkpoint：有则切换到联合模型，无则回退 NumPy+BKT。
> 业务代码、`DiagnosisReport` 契约、下游雷达/归因/推荐**完全不变**。

**模型**
- `NeuralCDNet`（[torch_models.py](../backend/app/modules/diagnosis/torch_models.py)）：学生掌握 `hs=σ(student_emb)` 可解释；
  `PosLinear` 正权重交互层（每步后 `clamp_(min=0)`，即原文 NoneNegClipper）保证单调性。
  工程取舍：隐层激活用 **ReLU**（同样单调、但不饱和），避免「多层 sigmoid + 小正权重」的梯度消失，使小样本稳定收敛。
- `DKTNet`：LSTM(hidden=32)+Dropout，输入 (知识点×对错) 的 2K one-hot 序列 → 每知识点下一刻答对概率。

**联合损失**　`L = BCE_ncd + α·BCE_dkt + β·Consistency`（[joint_trainer.py](../backend/app/modules/diagnosis/joint_trainer.py)）
- `Consistency`：把 DKT 序列末端的「每知识点掌握」与 NeuralCD 学生画像 `hs` 对齐（仅约束已练知识点），
  使静态画像与动态趋势互相正则——这就是"联合"的实质。

**评估（合成集 next-step 预测，含 Oracle 贝叶斯上限）**

| 模型 | AUC | ACC |
|---|---|---|
| NeuralCD | 0.615 | 0.587 |
| DKT | 0.632 | 0.613 |
| 集成均值 | 0.632 | 0.612 |
| **Oracle（理论天花板）** | **0.671** | — |

掌握度可恢复性 `corr(estimated, θ_true) = 0.406`。模型 AUC 达 Oracle 的 ~94%，差距即数据内禀 Bernoulli 噪声——证明确实学到了能力结构而非过拟合。

**训练与服务**
- 训练：`python scripts/train_diagnosis.py` → 生成合成日志 → 联合训练 → 存 `artifacts/diagnosis_joint.pt`。
  *该 checkpoint 用合成数据训练，仅作机制演示；生产以真实脱敏作答日志重训。*
- 服务（[torch_backend.py](../backend/app/modules/diagnosis/torch_backend.py)）：
  - 新学生**静态掌握**：冻结训练好的题目参数与交互网络，用 Adam 在线估计该生 θ（MAP，冷启动友好）；
  - **动态掌握**：把该生作答序列喂入 DKT-LSTM，取末端每知识点答对概率。

### 3.4 自适应推荐
- ZPD：预测答对率落 [0.6,0.8] 优先。
- 遗忘曲线：`R = exp(−Δt/S)`，`S = 1+9·掌握度`（掌握越牢忘得越慢），到期则插入复习。
- 配比 70/20/10，短缺向薄弱倾斜补足；排除最近 3 题。

### 3.6 真实日志训练流水线与增量更新调度（已落地）
> 合成数据降级为「无日志时的冷启动兜底 + 演示流量模拟」；线上以真实作答日志驱动训练。

**数据接入**（[dataset.py](../backend/app/modules/diagnosis/dataset.py)）
- `LogRepository` 接口 → `InMemoryLogRepository`(包 STORE，可跑) / `SQLLogRepository`(MySQL/Mongo 生产 stub，支持 `WHERE ts>:since` 增量)。
- `build_training_data_from_logs`：按学生分组、按时间排序，留每人最后一次作答做时序留出评估（真实日志无 θ_true/Oracle，自动跳过）。

**一次 run 的全流程**（[pipeline.py](../backend/app/modules/diagnosis/pipeline.py)）
```
接入 → 构造训练集 → [增量则热启动] → 联合训练 → 评估(AUC/ACC) → 门控(不退化才晋升)
     → 版本化保存 checkpoints/diagnosis_joint_{version}.pt → 原子切换 served → 写 registry.json → 剪枝
```
- **热启动（增量）**：只迁移「服务期真正用到的共享参数」(题目难度/区分度、交互网络、DKT)；学生 embedding 每轮按当前学生表重置（线上诊断用在线 θ 估计，不依赖训练期学生 embedding）。
- **门控防退化**：`ensemble_auc ≥ 在线版本 - ε` 且 `>0.5` 才晋升，否则保留旧模型、仅归档候选。
- **原子切换**：写临时文件后 `os.replace`，服务侧绝不会读到半成品。
- **可追溯**：`registry.json` 记录每次 version/时间/数据量/指标/是否晋升/base_version。

**增量更新调度**（[scheduler.py](../backend/app/modules/diagnosis/scheduler.py)）
- MVP：`IntervalScheduler` 后台线程，按间隔检查 `should_run`（新增作答达阈值 **或** 距上次≥N 小时）再触发。
- 生产：cron / Airflow / K8s CronJob 调用 `python scripts/train_pipeline.py --once --incremental`（每日增量）+ `--full`（每周全量）。

**服务侧热加载**：流水线晋升后，`DiagnosisEngine.reload_if_updated()`（按 mtime）无重启切换模型；
运维可调 `POST /api/v1/admin/reload-model` 触发。

**端到端演示**：`python scripts/train_pipeline.py --demo` —— 模拟两天流量，全量 v1 → 增量 v2(AUC 0.582→0.620) → 注册表 → 热加载，一条命令跑完。

### 3.7 变式题生成（PRD 4.2，已落地）
> 核心原则：**绝不让大模型现编数学**（会算错），用「参数化模板 + 符号求解器」保证正确性。

**模板引擎**（[templates.py](../backend/app/modules/variant/templates.py)）
- 每模板 = 固定考点/数学模型 + 可采样参数 + **符号求解器**（答案算出，非生成）。
- 6 个模板覆盖导数极值 / 等差求和 / 余弦定理 / 基本不等式 / 古典概型 / 椭圆离心率，知识点对齐图谱。
- 改参数 + 换情境 + 变设问 → 无穷变式；答案、分步思维链、苏格拉底引导随题自动产出。

**情境库**（[scenarios.py](../backend/app/modules/variant/scenarios.py)）：科技/社会/生产/经济…10 大类，
应用型模板套用情境（如同一数列模型换"医院门诊量/工厂产量/地铁客流"），贴近高考应用化趋势。

**质量控制流水线**（[quality.py](../backend/app/modules/variant/quality.py)）
1. 规则校验：超纲知识点（须在图谱内）、选项互异、答案合法。
2. 难度/区分度预测：特征法（步数·能力层级·题型·数值量级），生产替换标定模型。
3. 去重 + **版权相似度**：与受版权语料相似度须 **≤0.30**（IP 合规）；变式与种子"结构相似"是设计使然，去重只拦近乎雷同(>0.98)。
4. 内容安全：敏感/超纲词机审。
→ 全部通过 → 进入**人工审核队列**（[review.py](../backend/app/modules/variant/review.py)，PENDING→APPROVED/REJECTED）；仅 APPROVED 可用。

**回流闭环**：审核通过的变式题 = 一个 `Problem`，经 `SOLVER.solve_problem` 走**同一套苏格拉底门控**
（首次仅引导、逐级揭示、绝不直接给答案），并可进入认知诊断与推荐。
高考期间该功能由合规闸门（`feature='variant'`）熔断。

### 3.8 主观题批改（PRD 5，已落地）
> 评分不靠大模型拍脑袋，用「评分细则 + 可度量特征」透明评分；生产替换为阅卷样本微调模型（接口不变）。

- **作文**（[essay.py](../backend/app/modules/grading/essay.py)）：高考标准 3 一级维度 × 4 二级维度（内容/表达/发展等级，满分 60），
  每个二级维度由一个检测器给 0~1 分率（切题/中心/论据/结构/文采/思辨…）；输出总分、各维度得分、优缺点、修改建议、范文指引；
  含**校准**（scale/offset，按月对齐人评分，偏差≤5分）与内容安全。
- **文综/理综**（[subjective.py](../backend/app/modules/grading/subjective.py)）：**采分点语义匹配**（关键词覆盖 + trigram 相似度）按点给分 + 逻辑结构评价 + 改进建议。
- 高考期间由合规闸门（`essay_grade`/`subjective_grade`）熔断。

### 3.9 MLOps：监控告警 / A-B 灰度 / 漂移检测（已落地）
- **监控告警**（[monitoring.py](../backend/app/modules/mlops/monitoring.py)）：引擎诊断埋点（调用量/时延 p50·p95/模型版本/灰度桶/预测均值），
  导出 Prometheus 文本（`GET /metrics`）；`AlertManager` 按规则触发（高时延、错误率、预测分布漂移、训练陈旧、AUC 下跌）。
- **A/B 灰度**（[ab.py](../backend/app/modules/mlops/ab.py)）：按 user_id 稳定哈希分流挑战者，在线累积冠军/挑战者的准确率·Brier·AUC，
  达样本量给「晋升/保持/回滚」决策；引擎 `set_canary()` 路由部分流量到挑战者，新模型**先灰度、达标再全量**。
- **漂移检测**（[drift.py](../backend/app/modules/mlops/drift.py)）：PSI 量化参考窗口 vs 当前窗口的考点/难度/时长（特征）与正确率（标签）分布漂移，
  `major` 触发告警并建议重训（接 `pipeline.should_run`）。
- 闭环：监控/漂移 → 告警 → 流水线增量重训（§3.6）→ 影子评估/灰度（A/B）→ 达标晋升 → 引擎热加载（§3.6）。

### 3.10 真实 OCR/LLM 接入（生产级，已落地）
> 没有真实 key 也已把生产客户端跑通——用**契约一致的假服务 + httpx.MockTransport**在真实 HTTP 协议层验证。

- **LLM 客户端**（[llm.py](../backend/app/modules/rag/llm.py) `OpenAICompatibleClient`）：对接 vLLM/DeepSeek/Qwen，
  生产健壮性 = 超时 + 指数退避重试 + JSON 结构化输出 + LRU 缓存 + 启动探活；**任何失败优雅降级到 Mock**，服务不中断；可注入 httpx.Client。
- **自由输入解题走真实模型**（[solver.py](../backend/app/modules/rag/solver.py) `_full_free_input`）：FULL 级给出完整解答，
  但**苏格拉底门控**（先引导后揭示）+ **内容安全 + 知识点对照图谱核验**（[guards.py](../backend/app/modules/rag/guards.py)）仍生效——
  仅"真实模型 + 内容安全 + 知识点可核验"才放行最终答案；Mock 模式坚决不杜撰。
- **作文批改走真实模型**（[essay_llm.py](../backend/app/modules/grading/essay_llm.py)）：大模型按细则返回 JSON 分数 →
  **按上限夹紧 + 缺项回退 rubric + 整体失败兜底 + 校准**，兼得语义理解与确定性护栏。
- **OCR 网关**（[parsing.py](../backend/app/modules/parsing.py) `HttpEduParser`）：统一 HTTP 契约对接百度/阿里云，
  超时/重试/**降级到本地解析并告警**。
- **联调/测试**（[fake_llm_server.py](../backend/scripts/fake_llm_server.py)）：契约一致的假 LLM/OCR，
  既能独立起服务真机联调，也能用 MockTransport 在单测里驱动真实客户端（[test_real_integration.py](../backend/tests/test_real_integration.py)）。

### 3.11 错题本智能复习排程（间隔重复，已落地）
> 不只是"错题列表"，而是自动决定每道错题**何时该复习**，把有限时间花在最易遗忘的题上。

- **排程算法**（[review/scheduler.py](../backend/app/modules/review/scheduler.py)）：SM-2 间隔重复 + 艾宾浩斯遗忘曲线。
  首次做错 → 当日到期(学习态)；每次复习按回忆质量(对错+快慢→0~5)更新难度因子 ease 与间隔：答对则间隔按 ease 增长，
  答错则重学(间隔回落、ease 下降)；**低掌握度知识点缩短间隔、高掌握度拉长**；间隔≥21 天且复习≥4 次 → 毕业(移出活跃队列，再错复活)。
- **每日队列**（[review/book.py](../backend/app/modules/review/book.py)）：按**复习紧迫度**(逾期 + 遗忘程度(1-保持率) + 考点权重 + 学习态)排序，
  当日上限截断(配合防沉迷)；另提供统计与未来 7 天到期预测。
- **接入**：`/answer` 命中错题视为一次复习并更新排程，否则答错即入册；保持率 R=exp(-decay·elapsed/interval)（到期≈90%）。
- 错题复习属 `feature='review'`，**高考熔断期间仍开放**。

### 3.12 多学科扩展（数学 + 物理 + 化学 + 生物，已落地）
> 系统自始即「学科无关」设计（`Subject` 枚举 + subject 字段 + 模块化诊断/推荐/变式），扩科=填内容 + 按学科切片。

- **统一知识图谱 + 题库**（[seed_data_science.py](../backend/app/data/seed_data_science.py)）：物理/化学/生物概念与题目并入同一 KG/BANK，
  题干、苏格拉底引导、解题步骤、易错点齐全；**跨学科边**落实规格书示例（光合作用⇄化学平衡、简谐运动⇄三角函数、遗传⇄概率、欧姆定律⇄原电池）。
- **按学科切片**：`engine.diagnose(subject=...)` 掌握度估计仍用全部作答（不浪费跨学科信号），但报告（知识点/雷达/薄弱/错误画像/n_responses）仅呈现该学科，互不串味；
  `recommend(subject=...)` 仅推该学科题（缺省按学生已作答学科）；`build_cold_start_test(subject=...)` 出该学科卷。
- **科学变式模板**：运动学/欧姆定律/物质的量/遗传概率等，同样「符号求解保证正确」（[test_multisubject.py](../backend/tests/test_multisubject.py) 独立重算验证）。
- **复用零改动**：苏格拉底解题、变式质检/审核、主观题采分点批改、错题复习排程、MLOps —— 对任意学科直接生效。
- API：`GET /subjects`、`/diagnosis/{uid}?subject=physics`、`/recommend/{uid}?subject=chemistry`、`/diagnosis/cold-start?subject=biology`。

### 3.13 真实向量检索（bge + Milvus）与 GraphRAG（已落地）
> 没有 Milvus/bge 也已跑通生产路径：bge 走 HTTP（MockTransport 可测），向量库默认「内存真实余弦」（Milvus 契约对照实现）。

- **嵌入**（[embeddings.py](../backend/app/modules/rag/embeddings.py)）：`BGEHttpEmbedder` 对接 OpenAI/TEI 兼容 `/embeddings`（bge-large-zh / bge-m3），
  非对称检索给查询加指令前缀、超时重试、L2 归一化、失败回退 HashingEmbedder；`BGELocalEmbedder` 为本地 FlagEmbedding stub。
- **向量库**（[vectorstore.py](../backend/app/modules/rag/vectorstore.py)）：`VectorStore` 抽象；`InMemoryVectorStore`（NumPy 真实余弦 + 标量过滤，默认/可跑/检索质量真实）；
  `MilvusVectorStore`（pymilvus，HNSW + COSINE + 按学科标量过滤，生产）。
- **GraphRAG**（[graphrag.py](../backend/app/modules/rag/graphrag.py)）：① 实体链接（查询嵌入 ↔ 知识点描述嵌入 Top-K，替代旧版子串匹配）
  ② 带边权多跳扩散（先修/后继/同模块/**跨学科**，relevance=入口相似度×decay^hop×边权，**跨学科边双向**桥接）
  ③ chunk 图相关性打分。实测「三角函数」查询经跨学科桥召回「简谐运动（物理）」。
- **重排序**：`BGEHttpReranker`（bge-reranker-large `/rerank`，TEI 兼容，失败降级）。
- **融合**（[retriever.py](../backend/app/modules/rag/retriever.py)）：BM25 + Dense(向量库) + GraphRAG，min-max 归一加权（0.3/0.4/0.3），支持按学科过滤。
- 切换：`EMBEDDER_BACKEND=bge_http`、`VECTOR_STORE=milvus`、`RERANKER_BACKEND=bge_http`，不可用自动回退。

### 3.14 前端（已落地）
> 两套前端对接同一 FastAPI（已开 CORS），见 [frontend/](../frontend)。

- **管理后台（Vue3 + Vite）**[frontend/admin-vue](../frontend/admin-vue)：教师/运营端。四页——概览（学科/监控告警/A-B 灰度/PSI 漂移）、
  学情诊断（跨学科能力雷达 + 薄弱点 + ZPD 推荐，手写 SVG 雷达图无图表库依赖）、变式题审核（生成→质检→通过/驳回）、错题复习（到期队列+预测）。
  **已在本机 Vite 构建并浏览器联调通过**（也借此实跑揪出并修复了 recommend 的一处 `KeyError` 真 bug）。
- **学生端（React Native / Expo）**[frontend/student-rn](../frontend/student-rn)：底部 4 Tab——诊断（雷达）、苏格拉底解题（三级门控，绝不直接给答案）、今日推荐、错题本（SM-2 复习）。
  `npx expo start` 运行；`app.json` 的 `extra.apiBase` 配后端地址（Android 模拟器 `10.0.2.2`，真机用 LAN IP）。

### 3.15 AI 提分规划师（考生最需要的功能，已落地）
> 回答考生命门："距高考只剩 N 天、每天就这点时间，先补哪科哪个点最提分？" —— 时间预算下的**提分性价比最优化**。

- **考点蓝图**（[exam_blueprint.py](../backend/app/data/exam_blueprint.py)）：各学科各模块的高考分值占比，按知识点均摊得每点「高考权重(分)」。
- **优化模型**（[planner.py](../backend/app/modules/planner/planner.py)）：
  - 学习曲线 `m→1-(1-m)·e^(-k·t)`（凹性/边际递减），k=可学性（低层级考点提分更快）。
  - **性价比 ROI = 权重×(1-掌握度)×k**（高分值 + 低掌握 + 易提分 → 最该先补）。
  - **贪心边际分配** + **前置门控/前置增益**（先打地基再主攻，前置薄弱点对其解锁的高价值考点加权）。
  - **倒计时/熔断感知编排**：按距高考天数把投入摊到每天、**跨学科交错**（交错练习优于集中练）、每天嵌入当日错题复习；高考熔断日仅安排复习。
  - 产出：提分性价比排序、每日任务清单、**预计提分**（模型估计 + 诚实免责）。
- 与全栈打通：诊断(掌握度)→ 蓝图(分值)→ 规划(ROI)→ 推荐(每点配套题)→ 错题本(每日复习)；按学科可切片。
- API：`POST /plan {user_id, daily_minutes, subject?, days_left?}`；前端 Vue「提分规划」页 + RN「规划」Tab。

### 3.16 模考估分 + 真实模考反馈闭环（已落地）
> 把规划从"基于诊断的理论估计"升级为"被真实模考校准的闭环"：真实模考 = 反馈信号。

- **估分**（[predictor.py](../backend/app/modules/exam/predictor.py)）：`Σ(模块分值×模块掌握度)×应试折扣`，叠加由真实模考拟合的校准偏置 → 各科/总分 + 置信带。
- **真实模考校准**（[mock_store.py](../backend/app/modules/exam/mock_store.py)）：录入真实模考分时快照模型当时预测，拟合每科**偏置 offset**（收缩防少样本过拟合）纠正系统性高/低估；计算趋势。
- **反馈信号**（[feedback.py](../backend/app/modules/exam/feedback.py)）：只取「诊断看不到的**新信息**」——**应试丢分**（会做却失分=raw 预测−真实）+ **退步趋势** → 各科规划加权（知识薄弱本身已由 base ROI 体现，不重复计入）。
- **回灌规划**：各科加权乘进 ROI → 规划把时间更多投向"真实考场上最该补"的科目；计划头部显示**校准后的预计分**与反馈说明。
- 闭环：诊断估分 → 录入真实模考 → 校准 + 识别应试丢分 → 重排规划。API：`POST /mock`、`GET /score/{uid}`、`GET /mock/{uid}`，`/plan` 自动含反馈。前端 Vue/RN 规划页可录入模考。

### 3.17 应试丢分细分到题型 + 限时训练推荐（已落地）
> 把上一节的"应试丢分"从**学科级**下钻到**题型级**：丢在哪类题（选择/填空/解答·易中难压轴）、什么原因，再开出精准的限时训练。

- **卷面结构**（[exam_paper.py](../backend/app/data/exam_paper.py)）：各科卷面按区块建模——`Section(题型 qtype, 分值, 难度档 tier∈易/中/难/压轴, 建议用时, 丢分主因)`；数学 5 区块合计 150 分（选择基础 30 / 选择压轴 10 / 填空 20 / 解答中档 46 / 解答压轴·最后一问 44），物理/化学/生物同构。
- **题型丢分归因**（[sections.py](../backend/app/modules/exam/sections.py)）：按学科掌握度 `sm` 与难度档估"**该拿多少**"——`attain(易)=min(1,0.45+0.6·sm)`（易题高地板，弱生也该拿大部分）、`中=sm`、`难=0.85·sm`、`压轴=0.55·sm`（压轴强生也只约一半）；`应得=分值×attain`，`丢分=max(0, 应得−实得)`。**只分析填了的区块**。
- **限时训练**（`_drill`）：按题型/档位给出可执行处方——选择(易) 8 题/12min「正确率≥90%，不在简单题手滑」；难选择 6 题/15min「特值/排除秒杀」；压轴大题 3 题/25min「**只做最后一问，抢前两步的分**」。可挽回分按档位折算（易 1.0 / 中 0.9 / 难 0.6 / 压轴 0.4），**按可挽回分降序**——优先补"易/中该拿却丢"的分。
- **织入计划**（[planner.py](../backend/app/modules/planner/planner.py) `_schedule`）：限时训练作为**每天首个任务**（非熔断日），直击模考暴露的应试丢分；其后才是攻坚 + 错题复习。
- **健壮性**：录入得分在 `analyze` 处夹紧到 `[0, 满分]`（脏数据如 30 分题误填 999 不会扭曲归因），前端输入框同步加 `min/max` 边界。
- 闭环：录入分题型得分 → 题型级丢分归因 → 限时训练（排序）→ 自动排进每日首项。API：`POST /mock`（含 `section_scores`）、`GET /execution/{uid}`、`GET /exam/paper`，`/plan` 自动织入。前端 Vue/RN 规划页可"按题型录入"，并**完整呈现归因表**（题型 | 难易 | 应得 | 实得 | 丢分 | 主因 + 全科"会做却丢"总分），再展示限时训练——先让学生看清"丢在哪"，再给"怎么练"。超常发挥的区块（实得>应得）丢分显示"·"，绝不制造丢分。

## 4. 技术栈与部署

- 后端：Python 3.10+ / FastAPI（高性能接口可用 Go 旁路）。MVP 仅需 `fastapi/uvicorn/pydantic/numpy`。
- 数据：MySQL（结构化）+ MongoDB（非结构化）+ NebulaGraph（图谱）+ Milvus（向量）。
- 大模型：Transformers/PEFT/TRL 训练，vLLM 推理；**云端 70B（复杂推理）+ 边缘端 7B（基础解析/引导）混合部署**。
- 基础设施：Docker + Kubernetes + 阿里云/腾讯云（华东，数据境内）。
- 监控：Prometheus + Grafana + ELK。

```
[客户端 RN/Web] ─HTTPS─► [API 网关] ─► [FastAPI 业务] ─► [边缘 7B / 云端 70B (vLLM)]
                                          │
                          ┌───────────────┼───────────────┬───────────────┐
                       [MySQL]        [MongoDB]       [NebulaGraph]     [Milvus]
```

## 5. Mock → 生产 替换点（接口不变，配 `.env` 即切换）

| 能力 | MVP 实现 | 生产 | 切换开关 |
|---|---|---|---|
| OCR/公式 | MockEduParser | **HttpEduParser ✅** → 百度 PP-FormulaNet / 阿里云 | `OCR_ENDPOINT` |
| 嵌入 | HashingEmbedder | **BGEHttpEmbedder ✅** → bge-large-zh / bge-m3 | `EMBEDDER_BACKEND` |
| 向量库 | **InMemoryVectorStore ✅(真实余弦)** | **MilvusVectorStore ✅** | `VECTOR_STORE` |
| 重排 | HeuristicReranker | **BGEHttpReranker ✅** → bge-reranker-large | `RERANKER_BACKEND` |
| LLM | MockSolverLLM | **OpenAICompatibleClient ✅** → DeepSeek-R1/Qwen2(vLLM) | `LLM_BACKEND` |
| 图谱 | 内存 KnowledgeGraph | NebulaGraph | （仓储层替换）|
| 存储 | 内存 Store | MySQL + MongoDB（AES-256）| （仓储层替换）|
| 认知诊断 | NeuralCD(np)+BKT | **NeuralCD+DKT 联合训练(torch)** ✅已落地 | engine 自动检测 torch+checkpoint |

## 6. 质量保障
- 后端单测 **118 项**全绿：合规 / 诊断(NeuralCD+DKT) / 苏格拉底门控 / 推荐 / 训练流水线 / 变式题 / 主观题批改 / MLOps / 真实 OCR/LLM / 错题本复习排程 / 多学科(数理化生) / 真实向量检索(bge)+GraphRAG / AI 提分规划师 / 模考估分 + 真实模考反馈闭环(校准·应试丢分识别·规划重排) / **应试丢分细分到题型 + 限时训练推荐**。
- 前端：Vue3 管理后台已 Vite 构建 + 浏览器联调通过；React Native 学生端可 `npx expo start` 运行。
- 运行：`pytest -q`（全绿）；演示脚本 `demo.py`（核心链路）/ `demo_variant.py`（变式题）/ `demo_grading.py`（主观题批改）/ `demo_mlops.py`（监控·灰度·漂移）/ `train_diagnosis.py`（单次联合训练）/ `train_pipeline.py --demo`（真实日志流水线+增量调度）。
- 可观测：解题可追溯（`retrieved_context_ids`）、推荐可解释（`rationale`）、诊断可审计（雷达/归因）——同时满足算法备案的"可解释"要求。
