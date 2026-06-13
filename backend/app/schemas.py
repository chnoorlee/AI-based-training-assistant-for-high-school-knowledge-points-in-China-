"""全量数据契约（Pydantic v2）。

这是各模块之间、以及 API 对外的统一 JSON 契约。所有"解析输出""诊断报告""推荐列表"
都序列化为这里定义的结构，满足 PRD「统一输出为 JSON 格式」的要求。
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """时区感知的 UTC 当前时间（替代已弃用的 datetime.utcnow）。"""
    return datetime.now(timezone.utc)

# ──────────────────────────────────────────────────────────────
# 枚举：教育语义
# ──────────────────────────────────────────────────────────────


class Subject(str, Enum):
    MATH = "math"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    # 后续可继续扩展：chinese / english / politics / history / geography


class ProblemType(str, Enum):
    CHOICE = "choice"  # 选择题
    BLANK = "blank"  # 填空题
    SOLUTION = "solution"  # 解答题


class MasteryLevel(str, Enum):
    """知识掌握程度 4 级（PRD 3.1）。"""

    UNMASTERED = "unmastered"  # 未掌握
    INITIAL = "initial"  # 初步掌握
    BASIC = "basic"  # 基本掌握
    PROFICIENT = "proficient"  # 熟练掌握


class ErrorType(str, Enum):
    """错误类型 5 类（PRD 3.1）。"""

    CONCEPT = "concept"  # 概念误解
    CALCULATION = "calculation"  # 计算错误
    MISREAD = "misread"  # 审题失误
    LOGIC = "logic"  # 逻辑混乱
    TIME = "time"  # 时间管理不当


class AbilityLevel(str, Enum):
    """能力层级 6 级（布鲁姆，PRD 3.1）。"""

    MEMORY = "memory"  # 记忆
    UNDERSTAND = "understand"  # 理解
    APPLY = "apply"  # 应用
    ANALYZE = "analyze"  # 分析
    SYNTHESIZE = "synthesize"  # 综合
    CREATE = "create"  # 创新


class RevealLevel(int, Enum):
    """解题揭示级别——核心合规门控。"""

    HINT = 0  # 仅 3 个苏格拉底引导问题，绝不含答案
    GUIDED = 1  # 分步引导（不直接给最终答案值）
    FULL = 2  # 完整思维链 + 最终答案（须在 HINT/GUIDED 之后）


# ──────────────────────────────────────────────────────────────
# 知识图谱 & 题目
# ──────────────────────────────────────────────────────────────


class Concept(BaseModel):
    """知识点（知识图谱节点）。"""

    id: str
    name: str
    subject: Subject = Subject.MATH
    module: str = ""  # 所属模块，如「函数与导数」
    ability: AbilityLevel = AbilityLevel.UNDERSTAND
    prereq_ids: list[str] = Field(default_factory=list)  # 先修知识点
    cross_subject_ids: list[str] = Field(default_factory=list)  # 跨学科关联


class Problem(BaseModel):
    """题目（题库节点 / 解析输出的核心结构）。"""

    id: str
    subject: Subject = Subject.MATH
    type: ProblemType = ProblemType.SOLUTION
    concept_ids: list[str] = Field(default_factory=list)
    difficulty: float = 0.5  # 难度系数 0~1（越大越难）
    discrimination: float = 0.5  # 区分度 0~1
    ability: AbilityLevel = AbilityLevel.APPLY
    stem: str = ""  # 题干（LaTeX）
    options: dict[str, str] = Field(default_factory=dict)  # 选择题选项 {"A": "..."}
    answer: str = ""  # 标准答案
    solution_steps: list[str] = Field(default_factory=list)  # 解题步骤（思维链）
    socratic_questions: list[str] = Field(default_factory=list)  # 苏格拉底引导问
    common_errors: list[str] = Field(default_factory=list)  # 易错点
    source: str = ""  # 来源（人教/真题/模拟，含授权标记）


class ParsedProblem(BaseModel):
    """① 多模态解析的统一输出（PRD 1.1）。"""

    problem_id: str
    subject: Subject = Subject.MATH
    type: ProblemType = ProblemType.SOLUTION
    stem: str = ""
    options: dict[str, str] = Field(default_factory=dict)
    answer: str = ""  # 若图片中含作答区识别到的答案
    latex_blocks: list[str] = Field(default_factory=list)  # 识别出的公式 LaTeX
    concept_ids: list[str] = Field(default_factory=list)  # 知识点（图谱挂载）
    difficulty: float = 0.5
    handwriting_steps: list[HandwritingStep] = Field(default_factory=list)
    parse_confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)


class HandwritingStep(BaseModel):
    """手写解题过程的一步（PRD 1.1：区分草稿/正式解答、标记错误步骤）。"""

    index: int
    text: str
    region: str = "answer"  # draft（草稿） / answer（正式解答）
    is_error: bool = False
    error_type: Optional[ErrorType] = None
    note: str = ""


# ──────────────────────────────────────────────────────────────
# 作答记录
# ──────────────────────────────────────────────────────────────


class ResponseRecord(BaseModel):
    user_id: str
    problem_id: str
    correct: bool
    selected: str = ""  # 选择题作答
    time_spent_s: float = 0.0
    ts: datetime = Field(default_factory=utcnow)
    concept_ids: list[str] = Field(default_factory=list)
    difficulty: float = 0.5


# ──────────────────────────────────────────────────────────────
# ③ 认知诊断报告
# ──────────────────────────────────────────────────────────────


class ConceptMastery(BaseModel):
    concept_id: str
    concept_name: str
    score: float  # 掌握度 0~1
    level: MasteryLevel
    predicted_correct_prob: float  # 下一题预测答对概率


class RadarAxis(BaseModel):
    module: str  # 模块（雷达图一个轴）
    score: float  # 0~1


class DiagnosisReport(BaseModel):
    """可解释诊断结果：雷达图 + 知识点掌握 + 错误画像（PRD 3.1 可解释性）。"""

    user_id: str
    subject: Subject = Subject.MATH
    concept_mastery: list[ConceptMastery] = Field(default_factory=list)
    weak_concepts: list[str] = Field(default_factory=list)  # 薄弱知识点 id（按优先级）
    radar: list[RadarAxis] = Field(default_factory=list)
    error_profile: dict[str, float] = Field(default_factory=dict)  # 错误类型分布
    ability_profile: dict[str, float] = Field(default_factory=dict)  # 能力层级分布
    overall_mastery: float = 0.0
    n_responses: int = 0
    explanation: str = ""  # 自然语言解读


# ──────────────────────────────────────────────────────────────
# ② 解题（强制苏格拉底引导）
# ──────────────────────────────────────────────────────────────


class FactCheck(BaseModel):
    """幻觉抑制：对输出知识点的二次核验。"""

    verified_concepts: list[str] = Field(default_factory=list)
    unverified_claims: list[str] = Field(default_factory=list)  # 标记为待人工复核
    passed: bool = True


class SolveRequest(BaseModel):
    user_id: str
    problem_id: Optional[str] = None  # 命中题库时
    stem: Optional[str] = None  # 自由输入题干
    reveal_level: RevealLevel = RevealLevel.HINT


class SolveResponse(BaseModel):
    problem_id: str
    reveal_level: RevealLevel
    socratic_questions: list[str] = Field(default_factory=list)
    guided_steps: list[str] = Field(default_factory=list)
    chain_of_thought: list[str] = Field(default_factory=list)
    final_answer: Optional[str] = None  # 仅 FULL 且经过引导后给出
    knowledge_points: list[str] = Field(default_factory=list)
    retrieved_context_ids: list[str] = Field(default_factory=list)
    fact_check: FactCheck = Field(default_factory=FactCheck)
    notice: str = ""  # 合规/引导提示语


# ──────────────────────────────────────────────────────────────
# ④ 推荐
# ──────────────────────────────────────────────────────────────


class RecommendReason(str, Enum):
    WEAKNESS = "weakness"  # 针对知识漏洞（强化）
    CONSOLIDATE = "consolidate"  # 巩固已掌握（复习/遗忘曲线）
    STRETCH = "stretch"  # 拓展提高


class RecommendItem(BaseModel):
    problem_id: str
    concept_ids: list[str]
    difficulty: float
    reason: RecommendReason
    predicted_correct_prob: float  # 期望落在 ZPD（0.6~0.8）
    rationale: str = ""


class RecommendList(BaseModel):
    user_id: str
    items: list[RecommendItem] = Field(default_factory=list)
    mix: dict[str, int] = Field(default_factory=dict)  # 各类占比（目标 70/20/10）
    generated_at: datetime = Field(default_factory=utcnow)


# ──────────────────────────────────────────────────────────────
# 合规
# ──────────────────────────────────────────────────────────────


class ComplianceStatus(BaseModel):
    allowed: bool
    feature: str
    reason: str = ""
    code: str = "ok"  # ok / gaokao_blackout / daily_limit / night_lock / minor_unverified
    retry_after_minutes: Optional[int] = None
    allowed_features: list[str] = Field(default_factory=list)  # 受限时仍开放的功能


# ──────────────────────────────────────────────────────────────
# 变式题生成（PRD 4.2）
# ──────────────────────────────────────────────────────────────


class VariantReviewStatus(str, Enum):
    AUTO_REJECTED = "auto_rejected"  # 自动质检未通过，不入审核队列
    PENDING = "pending"  # 通过自动质检，待一线教师人工审核
    APPROVED = "approved"  # 人工审核通过，可入库使用
    REJECTED = "rejected"  # 人工审核驳回


class VariantQualityReport(BaseModel):
    """变式题质量控制报告（规则校验 + 难度预测 + 相似度/版权 + 内容安全）。"""

    rule_passed: bool = True
    rule_issues: list[str] = Field(default_factory=list)
    predicted_difficulty: float = 0.5
    predicted_discrimination: float = 0.5
    dedup_similarity: float = 0.0  # 与题库/同批最相近者的文本相似度（防重复）
    copyright_similarity: float = 0.0  # 与受版权保护语料的最大相似度（须 ≤0.30）
    content_safe: bool = True
    safety_issues: list[str] = Field(default_factory=list)
    auto_passed: bool = True  # 全部自动门通过 → 进入人工审核
    notes: list[str] = Field(default_factory=list)


class GeneratedVariant(BaseModel):
    id: str
    template_id: str
    source_problem_id: Optional[str] = None
    scenario_category: Optional[str] = None
    problem: Problem  # 生成的完整题目（含题干/选项/答案/思维链/苏格拉底引导/知识点）
    quality: VariantQualityReport = Field(default_factory=VariantQualityReport)
    review_status: VariantReviewStatus = VariantReviewStatus.PENDING
    reviewer: Optional[str] = None
    review_note: str = ""


class VariantGenerateRequest(BaseModel):
    user_id: str
    problem_id: Optional[str] = None  # 以某题为种子（取其考点对应模板）
    concept_id: Optional[str] = None  # 或直接指定考点
    count: int = 3
    scenario_category: Optional[str] = None  # 指定情境大类，缺省随机


# ──────────────────────────────────────────────────────────────
# 主观题批改（PRD 5）
# ──────────────────────────────────────────────────────────────


class DimensionScore(BaseModel):
    name: str  # 一级维度，如 内容/表达/发展等级
    max_score: float
    score: float
    sub_scores: dict[str, float] = Field(default_factory=dict)  # 二级维度得分
    comment: str = ""


class EssayGradeRequest(BaseModel):
    user_id: str
    prompt: str = ""  # 作文题/材料
    text: str  # 学生作文
    genre: str = "议论文"


class EssayGradeResult(BaseModel):
    total: float
    full_marks: float = 60.0
    dimensions: list[DimensionScore] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    exemplar_ref: str = ""  # 同类范文指引
    content_safe: bool = True
    confidence_band: float = 5.0  # 评分置信带（±分，对齐"偏差≤5分"）
    grader_backend: str = "rubric-mock"


class ScoringPoint(BaseModel):
    id: str
    description: str  # 采分点描述（标准答案要点）
    points: float
    keywords: list[str] = Field(default_factory=list)
    hit: bool = False
    similarity: float = 0.0
    awarded: float = 0.0
    matched_text: str = ""


class SubjectiveGradeRequest(BaseModel):
    user_id: str
    question: str = ""
    student_answer: str
    reference_points: list[dict] = Field(default_factory=list)  # [{description, points, keywords}]


class SubjectiveGradeResult(BaseModel):
    total: float
    full_marks: float
    points: list[ScoringPoint] = Field(default_factory=list)
    logic_score: float = 0.0  # 逻辑/论证结构分
    logic_comment: str = ""
    suggestions: list[str] = Field(default_factory=list)
    grader_backend: str = "semantic-mock"


# ──────────────────────────────────────────────────────────────
# 错题本智能复习排程（间隔重复 + 遗忘曲线）
# ──────────────────────────────────────────────────────────────


class ReviewStatus(str, Enum):
    LEARNING = "learning"  # 新错题 / 刚重学，未稳固
    REVIEW = "review"  # 进入间隔复习
    GRADUATED = "graduated"  # 已掌握，移出活跃队列（再错则复活）


class ReviewItem(BaseModel):
    problem_id: str
    concept_ids: list[str] = Field(default_factory=list)
    stem: str = ""
    status: ReviewStatus = ReviewStatus.LEARNING
    due: datetime
    interval_days: float = 0.0
    repetitions: int = 0
    ease: float = 2.5
    lapses: int = 0
    retention: float = 1.0  # 当前预测记忆保持率
    priority: float = 0.0  # 复习紧迫度（越大越该先复习）
    last_reviewed: Optional[datetime] = None


class ReviewQueue(BaseModel):
    user_id: str
    as_of: datetime = Field(default_factory=utcnow)
    due_count: int = 0  # 到期总数（未截断）
    capacity: int = 20  # 当日上限
    items: list[ReviewItem] = Field(default_factory=list)


class ReviewGradeRequest(BaseModel):
    user_id: str
    problem_id: str
    correct: bool
    time_spent_s: float = 0.0


class ReviewStats(BaseModel):
    user_id: str
    total: int = 0
    due_now: int = 0
    learning: int = 0
    review: int = 0
    graduated: int = 0
    lapses_total: int = 0
    avg_retention: float = 0.0


class ReviewForecastDay(BaseModel):
    date: str
    count: int


class ReviewForecast(BaseModel):
    user_id: str
    overdue: int = 0
    days: list[ReviewForecastDay] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# AI 提分规划师（时间预算下的提分性价比最优化）
# ──────────────────────────────────────────────────────────────


class PlanItem(BaseModel):
    concept_id: str
    concept_name: str
    subject: Subject = Subject.MATH
    mastery: float  # 当前掌握度
    exam_weight: float  # 高考权重（分）
    potential_points: float  # 可提分空间 = 权重×(1-掌握度)
    learnability: str  # 易 / 中 / 难
    roi: float  # 性价比：预计提分(分)/小时
    allocated_minutes: int = 0  # 计划投入分钟
    expected_gain: float = 0.0  # 该点预计提分
    reason: str = ""


class PlanTask(BaseModel):
    kind: str  # learn（攻坚）/ review（错题复习）
    concept_id: str = ""
    concept_name: str = ""
    subject: str = ""
    minutes: int = 0
    n_problems: int = 0
    detail: str = ""


class PlanDay(BaseModel):
    day_index: int
    date: str
    is_blackout: bool = False  # 高考熔断日 → 仅复习
    total_minutes: int = 0
    tasks: list[PlanTask] = Field(default_factory=list)
    note: str = ""


class StudyPlan(BaseModel):
    user_id: str
    subject: str = ""  # 空=全科
    days_left: int = 0
    daily_minutes: int = 120
    total_study_minutes: int = 0
    expected_score_gain: float = 0.0  # 预计总提分（模型估计，非承诺）
    projected_note: str = ""
    projected_score_now: float = 0.0  # 当前预计分（经模考校准）
    projected_full: float = 0.0  # 满分
    mock_calibrated: bool = False  # 是否已被真实模考校准
    feedback_note: str = ""  # 模考反馈对规划的影响说明
    priorities: list[PlanItem] = Field(default_factory=list)  # 提分性价比排序
    days: list[PlanDay] = Field(default_factory=list)
    timed_drills: list["TimedDrill"] = Field(default_factory=list)  # 题型级限时训练推荐


# ──────────────────────────────────────────────────────────────
# 模考估分 + 反馈闭环
# ──────────────────────────────────────────────────────────────


class SubjectScore(BaseModel):
    subject: str
    full_marks: float
    raw_predicted: float  # 基于掌握度的原始预测
    predicted: float  # 校准后预测
    actual: Optional[float] = None  # 最近一次真实模考得分
    execution_gap: float = 0.0  # 原始预测-真实（>0=应试丢分：会做却失分）
    priority_multiplier: float = 1.0  # 对规划的加权
    note: str = ""


class ScorePrediction(BaseModel):
    user_id: str
    subjects: list[SubjectScore] = Field(default_factory=list)
    total_predicted: float = 0.0
    total_full: float = 0.0
    band: float = 0.0  # 置信带 ±分
    calibrated: bool = False
    n_mocks: int = 0
    note: str = ""


class MockSubmit(BaseModel):
    user_id: str
    exam_name: str = "模考"
    scores: dict[str, float]  # {subject: 真实得分}
    full_marks: Optional[dict[str, float]] = None
    # 可选：分题型得分 {subject: {section_id: 得分}}，提供则做题型级丢分归因
    section_scores: Optional[dict[str, dict[str, float]]] = None


class SectionScore(BaseModel):
    section_id: str
    name: str
    qtype: str  # choice / blank / solution
    tier: str  # 易 / 中 / 难 / 压轴
    full: float
    got: Optional[float] = None
    expected: float = 0.0  # 按掌握度应得
    loss: float = 0.0  # 应得-实得（应试丢分）
    cause: str = ""


class TimedDrill(BaseModel):
    subject: str
    title: str
    qtype: str
    tier: str
    n_problems: int
    time_limit_min: int
    goal: str
    cause: str
    recoverable_points: float  # 预计可挽回分
    detail: str = ""


class SubjectExecution(BaseModel):
    subject: str
    sections: list[SectionScore] = Field(default_factory=list)
    total_loss: float = 0.0
    fixable_loss: float = 0.0  # 易/中档可挽回的丢分


class ExecutionReport(BaseModel):
    user_id: str
    has_section_data: bool = False
    subjects: list[SubjectExecution] = Field(default_factory=list)
    drills: list[TimedDrill] = Field(default_factory=list)
    note: str = ""


class MockRecord(BaseModel):
    exam_name: str
    date: str
    scores: dict[str, float]
    predicted_raw: dict[str, float]  # 提交时模型原始预测（用于校准）
    sections: dict = Field(default_factory=dict)  # {subject: {section_id: 得分}}


class MockHistory(BaseModel):
    user_id: str
    records: list[MockRecord] = Field(default_factory=list)
    trend: dict[str, float] = Field(default_factory=dict)  # 各科斜率（分/次）
    calibration: dict = Field(default_factory=dict)  # 各科 {offset, n, mae}


class PlanRequest(BaseModel):
    user_id: str
    daily_minutes: int = 120
    days_left: Optional[int] = None  # 缺省按高考日期自动计算
    subject: str = ""
    preview_days: int = 7  # 详细编排前 N 天（其余汇总）


# 解决前向引用
ParsedProblem.model_rebuild()
StudyPlan.model_rebuild()
