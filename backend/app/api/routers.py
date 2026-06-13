"""API 路由层。所有"做题/解析"类接口统一经过合规闸门（高考熔断 + 防沉迷）。

注意：合规判定使用真实当前时间——若在 23:00–06:00 或高考窗口内启动并调用，
解题/解析/推荐会被依规拦截（这是正确行为，非缺陷）。诊断报告、错题本不受影响。
"""
from __future__ import annotations

from typing import Optional

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core import compliance
from app.core.config import settings
from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.modules.diagnosis.engine import ENGINE
from app.modules.parsing import PARSER
from app.modules.rag.solver import SOLVER
from app.modules.recommend import RECOMMENDER
from app.modules.exam import feedback as exam_feedback
from app.modules.exam import sections as exam_sections
from app.modules.exam.mock_store import MOCK_BOOK
from app.modules.exam.predictor import PREDICTOR
from app.modules.grading.grader import ESSAY, SUBJECTIVE
from app.modules.planner.planner import PLANNER
from app.modules.review.book import REVIEW_BOOK
from app.modules.variant.generator import GENERATOR
from app.modules.variant.review import VARIANT_STORE
from app.schemas import (
    ComplianceStatus,
    DiagnosisReport,
    EssayGradeRequest,
    EssayGradeResult,
    ExecutionReport,
    GeneratedVariant,
    MockHistory,
    MockSubmit,
    ParsedProblem,
    PlanRequest,
    ScorePrediction,
    RecommendList,
    ResponseRecord,
    RevealLevel,
    StudyPlan,
    ReviewForecast,
    ReviewGradeRequest,
    ReviewItem,
    ReviewQueue,
    ReviewStats,
    SolveRequest,
    SolveResponse,
    SubjectiveGradeRequest,
    SubjectiveGradeResult,
    VariantGenerateRequest,
    VariantReviewStatus,
)
from app.services.store import STORE

router = APIRouter()


def enforce(feature: str, user_id: str) -> None:
    """合规闸门：不通过则抛 403，detail 为 ComplianceStatus。"""
    used = STORE.get_today_usage(user_id)
    status = compliance.check(feature, used_minutes_today=used)
    if not status.allowed:
        raise HTTPException(status_code=403, detail=status.model_dump())


# ── 健康检查 ────────────────────────────────────────────────
@router.get("/health")
def health() -> dict:
    return {"status": "ok", "subjects": KG.subjects(), "problems": len(BANK.problem_ids),
            "concepts": len(KG.all_ids())}


@router.get("/subjects")
def subjects() -> dict:
    return {"subjects": [
        {"subject": s, "concepts": len(KG.concepts_for_subject(s)),
         "problems": len(BANK.by_subject(s)), "modules": KG.modules_for_subject(s)}
        for s in KG.subjects()]}


# ── ① 解析 ─────────────────────────────────────────────────
class ParseIn(BaseModel):
    user_id: str
    text: str
    handwriting: Optional[list[dict]] = None


@router.post("/parse", response_model=ParsedProblem)
def parse(body: ParseIn) -> ParsedProblem:
    enforce("parse", body.user_id)
    STORE.ensure_user(body.user_id)
    return PARSER.parse(body.text, body.handwriting)


# ── 冷启动诊断测试 ──────────────────────────────────────────
@router.get("/diagnosis/cold-start")
def cold_start(user_id: str, n: int = 30, subject: str = "") -> dict:
    enforce("cold_start", user_id)
    ids = ENGINE.build_cold_start_test(n, subject=subject)
    # 只下发题面，不泄露答案
    items = [{"problem_id": p.id, "type": p.type.value, "stem": p.stem,
              "options": p.options, "concept_ids": p.concept_ids} for p in
             (BANK.get(i) for i in ids)]
    return {"user_id": user_id, "count": len(items), "est_minutes": min(15, len(items)),
            "items": items}


# ── 作答上报 ────────────────────────────────────────────────
class AnswerIn(BaseModel):
    user_id: str
    problem_id: str
    selected: Optional[str] = None
    correct: Optional[bool] = None
    time_spent_s: float = 0.0


@router.post("/answer")
def answer(body: AnswerIn) -> dict:
    p = BANK.get(body.problem_id)
    if p is None:
        raise HTTPException(404, "题目不存在")
    if body.selected is not None and p.options:
        correct = body.selected.strip().upper() == p.answer.strip().upper()
    else:
        correct = bool(body.correct)
    rec = ResponseRecord(user_id=body.user_id, problem_id=body.problem_id, correct=correct,
                         selected=body.selected or "", time_spent_s=body.time_spent_s,
                         concept_ids=list(p.concept_ids), difficulty=p.difficulty)
    STORE.add_response(rec)
    STORE.add_usage_minutes(body.user_id, body.time_spent_s / 60.0)
    # 接入复习排程：错题入册 / 命中错题则视为一次复习并更新排程
    rv = REVIEW_BOOK.record_attempt(body.user_id, body.problem_id, correct, body.time_spent_s)
    return {"ok": True, "correct": correct, "n_responses": STORE.n_responses(body.user_id),
            "review": {"scheduled": rv is not None,
                       "due": rv.due.isoformat() if rv else None,
                       "interval_days": rv.interval_days if rv else None,
                       "status": rv.status if rv else None}}


# ── ③ 诊断报告（熔断期间仍可查看）─────────────────────────────
@router.get("/diagnosis/{user_id}", response_model=DiagnosisReport)
def diagnosis(user_id: str, subject: str = "") -> DiagnosisReport:
    enforce("diagnosis_view", user_id)
    return ENGINE.diagnose(user_id, STORE.get_responses(user_id), subject=subject)


# ── ② 解题（强制苏格拉底引导）────────────────────────────────
@router.post("/solve", response_model=SolveResponse)
def solve(body: SolveRequest) -> SolveResponse:
    enforce("solve", body.user_id)
    if not body.problem_id and not body.stem:
        raise HTTPException(422, "problem_id 与 stem 至少提供一个")
    return SOLVER.solve(body)


# ── ④ 推荐 ─────────────────────────────────────────────────
@router.get("/recommend/{user_id}", response_model=RecommendList)
def recommend(user_id: str, n: int = 10, subject: str = "") -> RecommendList:
    enforce("recommend", user_id)
    report = ENGINE.diagnose(user_id, STORE.get_responses(user_id), subject=subject)
    return RECOMMENDER.recommend(user_id, report, STORE.get_responses(user_id),
                                 n=n, subject=subject)


# ── 错题本（始终开放）──────────────────────────────────────
@router.get("/wrongbook/{user_id}")
def wrongbook(user_id: str) -> dict:
    ids = STORE.get_wrongbook(user_id)
    items = [{"problem_id": p.id, "stem": p.stem,
              "concept_ids": p.concept_ids, "common_errors": p.common_errors}
             for p in (BANK.get(i) for i in ids) if p]
    return {"user_id": user_id, "count": len(items), "items": items}


def _prediction(user_id: str, report) -> ScorePrediction:
    an = exam_feedback.analyze(MOCK_BOOK, report, PREDICTOR, user_id)
    return PREDICTOR.predict(
        report, calibration=MOCK_BOOK.calibration(user_id),
        actuals=MOCK_BOOK.latest_actuals(user_id),
        multipliers={s: a["multiplier"] for s, a in an.items()},
        gaps={s: a["execution_gap"] for s, a in an.items()})


# ── AI 提分规划师（时间预算 + 倒计时 + 模考反馈 → 提分性价比最优计划）────
@router.post("/plan", response_model=StudyPlan)
def study_plan(body: PlanRequest) -> StudyPlan:
    enforce("review", body.user_id)  # 规划属复习范畴，熔断期仍可看
    report = ENGINE.diagnose(body.user_id, STORE.get_responses(body.user_id), subject=body.subject)
    review_due = REVIEW_BOOK.due_queue(body.user_id).due_count
    sw = exam_feedback.subject_weights(MOCK_BOOK, report, PREDICTOR, body.user_id)  # 模考反馈加权
    projection = _prediction(body.user_id, report)
    drills = exam_sections.execution_report(MOCK_BOOK, report, PREDICTOR).drills  # 题型级限时训练
    return PLANNER.plan(report, daily_minutes=body.daily_minutes, days_left=body.days_left,
                        subject=body.subject, review_due=review_due, preview_days=body.preview_days,
                        subject_weights=sw, projection=projection, timed_drills=drills)


# ── 模考估分 + 真实模考反馈闭环 ──────────────────────────────
@router.get("/score/{user_id}", response_model=ScorePrediction)
def score(user_id: str, subject: str = "") -> ScorePrediction:
    enforce("review", user_id)
    report = ENGINE.diagnose(user_id, STORE.get_responses(user_id), subject=subject)
    return _prediction(user_id, report)


@router.post("/mock", response_model=ScorePrediction)
def submit_mock(body: MockSubmit) -> ScorePrediction:
    enforce("review", body.user_id)
    report = ENGINE.diagnose(body.user_id, STORE.get_responses(body.user_id))
    MOCK_BOOK.submit(body.user_id, body.exam_name, body.scores, PREDICTOR, report,
                     body.full_marks, body.section_scores)
    return _prediction(body.user_id, report)  # 提交后立即返回校准后的新估分


@router.get("/mock/{user_id}", response_model=MockHistory)
def mock_history(user_id: str) -> MockHistory:
    return MOCK_BOOK.history(user_id)


@router.get("/exam/paper")
def exam_paper(subject: str = "") -> dict:
    """卷面结构（供前端渲染分题型录入）。"""
    from app.data.exam_paper import PAPER_BLUEPRINT
    src = {subject: PAPER_BLUEPRINT[subject]} if subject and subject in PAPER_BLUEPRINT else PAPER_BLUEPRINT
    return {s: [{"id": x.id, "name": x.name, "qtype": x.qtype, "points": x.points,
                 "tier": x.tier, "rec_minutes": x.rec_minutes} for x in secs]
            for s, secs in src.items()}


@router.get("/execution/{user_id}", response_model=ExecutionReport)
def execution(user_id: str) -> ExecutionReport:
    """题型级应试丢分分析 + 限时训练推荐（需录入分题型得分）。"""
    enforce("review", user_id)
    report = ENGINE.diagnose(user_id, STORE.get_responses(user_id))
    return exam_sections.execution_report(MOCK_BOOK, report, PREDICTOR)


# ── 错题本智能复习排程（间隔重复，熔断期间仍开放）────────────
@router.get("/review/queue/{user_id}", response_model=ReviewQueue)
def review_queue(user_id: str, limit: int = 20) -> ReviewQueue:
    enforce("review", user_id)
    return REVIEW_BOOK.due_queue(user_id, limit=limit)


@router.post("/review/grade", response_model=ReviewItem)
def review_grade(body: ReviewGradeRequest) -> ReviewItem:
    enforce("review", body.user_id)
    item = REVIEW_BOOK.grade(body.user_id, body.problem_id, body.correct, body.time_spent_s)
    if item is None:
        raise HTTPException(404, "该题不在错题复习表中")
    return item


@router.get("/review/stats/{user_id}", response_model=ReviewStats)
def review_stats(user_id: str) -> ReviewStats:
    return REVIEW_BOOK.stats(user_id)


@router.get("/review/forecast/{user_id}", response_model=ReviewForecast)
def review_forecast(user_id: str, days: int = 7) -> ReviewForecast:
    return REVIEW_BOOK.forecast(user_id, days=days)


# ── 合规自查 / 用量 ─────────────────────────────────────────
@router.get("/compliance", response_model=ComplianceStatus)
def compliance_check(user_id: str, feature: str = Query("solve")) -> ComplianceStatus:
    used = STORE.get_today_usage(user_id)
    return compliance.check(feature, used_minutes_today=used)


@router.get("/usage/{user_id}")
def usage(user_id: str) -> dict:
    return {"user_id": user_id, "today_minutes": round(STORE.get_today_usage(user_id), 1),
            "n_responses": STORE.n_responses(user_id)}


# ── 运维：诊断模型热加载（训练流水线晋升后调用，无需重启）────────────
@router.post("/admin/reload-model")
def reload_model() -> dict:
    changed = ENGINE.reload_if_updated()
    return {"reloaded": changed, "backend": ENGINE.backend_name}


# ── MLOps：监控 / 告警 / A-B 灰度 / 漂移 ─────────────────────
@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    from app.modules.mlops.monitoring import METRICS
    return METRICS.prometheus_text()


@router.get("/monitoring/alerts")
def monitoring_alerts() -> dict:
    from app.modules.mlops.monitoring import ALERTS, METRICS
    alerts = ALERTS.evaluate(METRICS)
    return {"snapshot": METRICS.snapshot(),
            "alerts": [a.__dict__ for a in alerts]}


@router.get("/ab/status")
def ab_status() -> dict:
    from app.modules.mlops.ab import AB
    return AB.report()


class ABConfigIn(BaseModel):
    enabled: bool
    canary_pct: int


@router.post("/ab/config")
def ab_config(body: ABConfigIn) -> dict:
    from app.modules.mlops.ab import AB
    AB.configure(body.enabled, body.canary_pct,
                 champion_version=AB.config.champion_version,
                 canary_version=AB.config.canary_version)
    return {"ok": True, "config": AB.config.__dict__}


@router.get("/drift/report")
def drift_report(hours: float = Query(24.0, description="当前窗口=最近 hours 小时")) -> dict:
    from app.modules.diagnosis.dataset import InMemoryLogRepository
    from app.modules.mlops.drift import detect_drift
    split = settings.now() - timedelta(hours=hours)
    rep = detect_drift(InMemoryLogRepository(STORE), split)
    return rep.__dict__


# ── ④ 变式题生成（高考期间熔断）────────────────────────────
@router.post("/variant/generate", response_model=list[GeneratedVariant])
def variant_generate(body: VariantGenerateRequest) -> list[GeneratedVariant]:
    enforce("variant", body.user_id)
    return GENERATOR.generate(body)


@router.get("/variant/review/queue", response_model=list[GeneratedVariant])
def variant_queue() -> list[GeneratedVariant]:
    return VARIANT_STORE.pending()


class VariantReviewIn(BaseModel):
    reviewer: str
    approve: bool
    note: str = ""


@router.post("/variant/review/{vid}", response_model=GeneratedVariant)
def variant_review(vid: str, body: VariantReviewIn) -> GeneratedVariant:
    v = VARIANT_STORE.review(vid, body.approve, body.reviewer, body.note)
    if v is None:
        raise HTTPException(404, "变式题不存在")
    return v


@router.get("/variant/{vid}", response_model=GeneratedVariant)
def variant_get(vid: str) -> GeneratedVariant:
    v = VARIANT_STORE.get(vid)
    if v is None:
        raise HTTPException(404, "变式题不存在")
    return v


class VariantSolveIn(BaseModel):
    user_id: str
    variant_id: str
    reveal_level: int = 0


@router.post("/variant/solve", response_model=SolveResponse)
def variant_solve(body: VariantSolveIn) -> SolveResponse:
    enforce("solve", body.user_id)
    v = VARIANT_STORE.get(body.variant_id)
    if v is None:
        raise HTTPException(404, "变式题不存在")
    if v.review_status != VariantReviewStatus.APPROVED:
        raise HTTPException(409, "该变式题未通过人工审核，不可用于解题")
    return SOLVER.solve_problem(body.user_id, v.problem, RevealLevel(body.reveal_level))


# ── ⑤ 主观题批改（高考期间熔断）────────────────────────────
@router.post("/grade/essay", response_model=EssayGradeResult)
def grade_essay(body: EssayGradeRequest) -> EssayGradeResult:
    enforce("essay_grade", body.user_id)
    return ESSAY.grade(body.prompt, body.text, body.genre)


@router.post("/grade/subjective", response_model=SubjectiveGradeResult)
def grade_subjective(body: SubjectiveGradeRequest) -> SubjectiveGradeResult:
    enforce("subjective_grade", body.user_id)
    return SUBJECTIVE.grade(body.question, body.student_answer, body.reference_points)


# ── 家长监护 ────────────────────────────────────────────────
class GuardianIn(BaseModel):
    child_user_id: str
    daily_limit_minutes: Optional[int] = None
    content_filter: Optional[bool] = None


@router.post("/guardian/setting")
def guardian_setting(body: GuardianIn) -> dict:
    STORE.set_guardian_setting(
        body.child_user_id,
        **{k: v for k, v in body.model_dump().items()
           if k != "child_user_id" and v is not None})
    return {"ok": True, "setting": STORE.get_guardian_setting(body.child_user_id)}
