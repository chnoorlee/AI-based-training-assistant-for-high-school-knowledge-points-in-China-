"""认知诊断引擎：NeuralCD（静态多知识点画像）+ BKT（动态掌握演化）混合。

产出可解释的 DiagnosisReport：知识点掌握 4 级、薄弱点排序、模块雷达图、
错误类型画像、能力层级画像、自然语言解读。并提供 30 题冷启动诊断蓝图与错误归因。
"""
from __future__ import annotations

import numpy as np

from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.modules.diagnosis.knowledge_tracing import BKT
from app.modules.diagnosis.neural_cd import NeuralCD
from app.schemas import (
    ConceptMastery,
    DiagnosisReport,
    ErrorType,
    MasteryLevel,
    RadarAxis,
    ResponseRecord,
    Subject,
)

# 掌握度 → 4 级阈值
_LEVEL_THRESHOLDS = [
    (0.40, MasteryLevel.UNMASTERED),
    (0.60, MasteryLevel.INITIAL),
    (0.80, MasteryLevel.BASIC),
    (1.01, MasteryLevel.PROFICIENT),
]
_NCD_WEIGHT = 0.6  # 混合权重：NeuralCD 静态画像
_BKT_WEIGHT = 0.4  # 混合权重：BKT 动态追踪


def score_to_level(score: float) -> MasteryLevel:
    for thr, lvl in _LEVEL_THRESHOLDS:
        if score < thr:
            return lvl
    return MasteryLevel.PROFICIENT


def classify_error(record: ResponseRecord, concept_mastery: float, n_concepts: int,
                   ability: str) -> ErrorType:
    """错误归因（启发式）。生产版结合手写步骤识别 + 模型，颗粒度更细。"""
    t = record.time_spent_s
    if t and t < 20 and record.difficulty >= 0.4:
        return ErrorType.MISREAD  # 用时过短却做难题 → 审题/急躁
    if concept_mastery < 0.40:
        return ErrorType.CONCEPT  # 该点掌握很弱 → 概念误解
    if n_concepts >= 2 and ability in ("analyze", "synthesize", "create"):
        return ErrorType.LOGIC  # 多知识点综合题 → 逻辑/推理链断裂
    if concept_mastery >= 0.60:
        return ErrorType.CALCULATION  # 本会却错 → 计算失误
    if t and t > 300:
        return ErrorType.TIME
    return ErrorType.LOGIC


class DiagnosisEngine:
    def __init__(self, torch_backend=None, auto_load_torch: bool = True) -> None:
        diff = BANK.difficulty_vector()
        disc = np.array([BANK.problems[pid].discrimination for pid in BANK.problem_ids])
        self.ncd = NeuralCD(BANK.q_matrix, diff, disc)
        self.bkt = BKT()
        self.concept_ids = BANK.concept_ids
        self.cidx = BANK.concept_index
        # PyTorch 联合模型（NeuralCD+DKT）：有 checkpoint 则自动启用，否则回退 NumPy 版
        self.torch_backend = torch_backend
        if self.torch_backend is None and auto_load_torch:
            try:
                from app.modules.diagnosis.torch_backend import TorchDiagnosisBackend
                self.torch_backend = TorchDiagnosisBackend.load_if_available()
            except Exception:
                self.torch_backend = None
        # 知识点顺序必须与训练时一致，否则弃用以防错位
        if self.torch_backend and list(self.torch_backend.concept_ids) != list(self.concept_ids):
            self.torch_backend = None
        # A/B 灰度：挑战者后端（可选）
        self.canary_backend = None

    def set_canary(self, backend, canary_pct: int) -> None:
        """部署挑战者模型并配置灰度比例（A/B 金丝雀）。"""
        from app.modules.mlops.ab import AB
        self.canary_backend = backend
        AB.configure(enabled=backend is not None and canary_pct > 0, canary_pct=canary_pct,
                     champion_version=getattr(self.torch_backend, "version", "—"),
                     canary_version=getattr(backend, "version", "—"))

    def _pick_backend(self, user_id: str):
        """按 A/B 路由选择服务后端，返回 (backend, version, bucket)。"""
        from app.modules.mlops.ab import AB
        if self.canary_backend is not None and AB.router.assign(user_id) == "canary":
            return self.canary_backend, getattr(self.canary_backend, "version", "canary"), "canary"
        return (self.torch_backend, getattr(self.torch_backend, "version", "numpy"),
                "champion")

    @property
    def backend_name(self) -> str:
        return ("torch(NeuralCD+DKT 联合训练)" if self.torch_backend
                else "numpy(NeuralCD+BKT)")

    def reload_if_updated(self) -> bool:
        """热加载：若 served checkpoint 有更新（被流水线晋升），无重启切换到新模型。"""
        import os
        from app.modules.diagnosis.torch_backend import DEFAULT_CKPT, TorchDiagnosisBackend
        if not os.path.exists(DEFAULT_CKPT):
            return False
        mtime = os.path.getmtime(DEFAULT_CKPT)
        cur = getattr(self.torch_backend, "mtime", None) if self.torch_backend else None
        if cur is not None and cur == mtime:
            return False
        nb = TorchDiagnosisBackend.load_if_available(DEFAULT_CKPT)
        if nb and list(nb.concept_ids) == list(self.concept_ids):
            self.torch_backend = nb
            return True
        return False

    def _estimate_mastery(self, responses: list[ResponseRecord], backend=None):
        """返回 (ncd_mastery[K], kt_known{concept->prob|None}, evidenced)。

        backend 给定（torch 联合模型，可能是冠军或灰度挑战者）时用之；否则 NumPy NeuralCD + BKT。
        下游融合/雷达/归因逻辑对两条路径完全一致。
        """
        item_idx, outcomes = [], []
        for r in responses:
            if r.problem_id in BANK.problem_index:
                item_idx.append(BANK.problem_index[r.problem_id])
                outcomes.append(1.0 if r.correct else 0.0)
        # 证据集合（两条路径共用）
        evidenced: set[str] = set()
        seq: dict[str, list[bool]] = {c: [] for c in self.concept_ids}
        for r in responses:
            cids = r.concept_ids or (BANK.problems[r.problem_id].concept_ids
                                     if r.problem_id in BANK.problems else [])
            for c in cids:
                if c in seq:
                    seq[c].append(r.correct)
                    evidenced.add(c)

        if backend is not None:
            ncd_mastery = backend.infer_static(item_idx, outcomes)
            # DKT 需要"主知识点 + 对错"的有序序列
            cseq, cout = [], []
            for r in responses:
                cids = r.concept_ids or (BANK.problems[r.problem_id].concept_ids
                                         if r.problem_id in BANK.problems else [])
                if cids and cids[0] in self.cidx:
                    cseq.append(self.cidx[cids[0]])
                    cout.append(1.0 if r.correct else 0.0)
            dkt_vec = backend.infer_dynamic(cseq, cout)
            kt_known = {c: float(dkt_vec[self.cidx[c]]) if c in evidenced else None
                        for c in self.concept_ids}
            return ncd_mastery, kt_known, evidenced

        # NumPy 回退
        ncd_mastery = self.ncd.estimate_student(item_idx, outcomes)
        kt_known = {c: self.bkt.trace(c, seq[c]) if seq[c] else None
                    for c in self.concept_ids}
        return ncd_mastery, kt_known, evidenced

    # ── 冷启动诊断蓝图（PRD 3.1：30 题 / 15 分钟 / 准确率≥80%）───────
    def build_cold_start_test(self, n: int = 30, subject: str = "") -> list[str]:
        """覆盖尽可能多的知识点与模块，难度由易到难，控制在 ~15 分钟。

        subject 为空=综合卷；指定学科则仅取该学科题。MVP 种子题有限，
        按「先覆盖各模块、再补难度梯度」择优返回；生产题库充足时严格取 30 题并按 CAT 动态选题。
        """
        pool = ([p.id for p in BANK.by_subject(subject)] if subject else list(BANK.problem_ids))
        chosen: list[str] = []
        seen_concepts: set[str] = set()
        for pid in sorted(pool, key=lambda p: BANK.problems[p].difficulty):
            cset = set(BANK.problems[pid].concept_ids)
            if cset - seen_concepts:
                chosen.append(pid)
                seen_concepts |= cset
            if len(chosen) >= n:
                return chosen
        for pid in sorted(pool, key=lambda p: BANK.problems[p].difficulty):
            if pid not in chosen:
                chosen.append(pid)
            if len(chosen) >= n:
                break
        return chosen

    # ── 主诊断 ─────────────────────────────────────────────
    def diagnose(self, user_id: str, responses: list[ResponseRecord],
                 subject: str = "") -> DiagnosisReport:
        """subject 为空=跨学科综合；指定学科则报告仅呈现该学科（掌握度估计仍用全部作答）。"""
        import time
        t0 = time.perf_counter()
        # A/B 路由：选服务后端（冠军 或 灰度挑战者）
        backend, version, bucket = self._pick_backend(user_id)
        # 1+2) 估计掌握度：NeuralCD 多知识点画像 + 知识追踪（torch 联合模型 或 NumPy+BKT）
        ncd_mastery, kt_known, evidenced = self._estimate_mastery(responses, backend)

        # 学科切片：目标知识点集合 + 本学科作答
        def _in_subject(c: str) -> bool:
            return (not subject) or KG.subject_of(c) == subject
        sub_responses = [r for r in responses if not subject or (
            r.problem_id in BANK.problems
            and BANK.problems[r.problem_id].subject.value == subject)]

        # 3) 融合 → 混合掌握向量
        hybrid = np.full(len(self.concept_ids), 0.5)
        for c, i in self.cidx.items():
            if c in evidenced:
                hybrid[i] = _NCD_WEIGHT * ncd_mastery[i] + _BKT_WEIGHT * kt_known[c]
        # 3b) 图传播：无证据知识点 ← 其后继（依赖它的知识点）表现推断
        for c, i in self.cidx.items():
            if c in evidenced:
                continue
            succ_scores = [hybrid[self.cidx[s]] for s in KG.successors_of(c)
                           if s in self.cidx and s in evidenced]
            if succ_scores:
                hybrid[i] = float(min(1.0, np.mean(succ_scores) + 0.10))  # 前置通常略易

        # 4) 逐知识点掌握 + 预测答对概率（按学科过滤）
        concept_mastery: list[ConceptMastery] = []
        for c in self.concept_ids:
            if not _in_subject(c):
                continue
            i = self.cidx[c]
            score = float(hybrid[i])
            items = [BANK.problem_index[p.id] for p in BANK.by_concept(c)]
            pred = (float(np.mean([self.ncd.predict_prob_for_mastery(hybrid, it) for it in items]))
                    if items else self.bkt.predict(score, c))
            concept_mastery.append(ConceptMastery(
                concept_id=c, concept_name=KG.name_of(c), score=round(score, 4),
                level=score_to_level(score), predicted_correct_prob=round(pred, 4)))

        # 5) 薄弱点（仅评估有证据/可推断者，<0.6 视为待巩固，按掌握升序）
        weak = sorted(
            [cm for cm in concept_mastery if cm.score < 0.60 and
             (cm.concept_id in evidenced or cm.score != 0.5)],
            key=lambda cm: cm.score)
        weak_ids = [cm.concept_id for cm in weak]

        # 6) 模块雷达图（按学科）
        radar: list[RadarAxis] = []
        modules = KG.modules_for_subject(subject) if subject else KG.modules()
        for m in modules:
            cs = [self.cidx[c] for c in KG.concepts_in_module(m)
                  if c in self.cidx and _in_subject(c)]
            if cs:
                radar.append(RadarAxis(module=m, score=round(float(np.mean(hybrid[cs])), 4)))

        # 7) 错误画像（按学科）
        err_counts: dict[str, int] = {}
        for r in sub_responses:
            if r.correct:
                continue
            cids = r.concept_ids or (BANK.problems[r.problem_id].concept_ids
                                     if r.problem_id in BANK.problems else [])
            cscore = float(np.mean([hybrid[self.cidx[c]] for c in cids if c in self.cidx])) \
                if cids else 0.5
            ability = (BANK.problems[r.problem_id].ability.value
                       if r.problem_id in BANK.problems else "apply")
            et = classify_error(r, cscore, len(cids), ability)
            err_counts[et.value] = err_counts.get(et.value, 0) + 1
        total_err = sum(err_counts.values())
        error_profile = ({k: round(v / total_err, 3) for k, v in err_counts.items()}
                         if total_err else {})

        # 8) 能力层级画像（按学科）
        ability_groups: dict[str, list[float]] = {}
        for c in self.concept_ids:
            if not _in_subject(c):
                continue
            ab = KG.get(c).ability.value if KG.get(c) else "understand"
            ability_groups.setdefault(ab, []).append(hybrid[self.cidx[c]])
        ability_profile = {k: round(float(np.mean(v)), 3) for k, v in ability_groups.items()}

        # 9) 总体掌握 + 解读（按学科）
        ev_scores = [hybrid[self.cidx[c]] for c in evidenced if _in_subject(c)]
        if not ev_scores:
            ev_scores = [cm.score for cm in concept_mastery] or [0.5]
        overall = round(float(np.mean(ev_scores)), 4)
        explanation = self._explain(weak, error_profile, overall, len(sub_responses))

        report = DiagnosisReport(
            user_id=user_id, subject=Subject(subject) if subject else Subject.MATH,
            concept_mastery=concept_mastery, weak_concepts=weak_ids,
            radar=radar, error_profile=error_profile, ability_profile=ability_profile,
            overall_mastery=overall, n_responses=len(sub_responses), explanation=explanation)
        # 监控埋点：调用量/时延/模型版本/灰度桶/预测均值
        try:
            from app.modules.mlops.monitoring import METRICS
            METRICS.record_serving("diagnose", (time.perf_counter() - t0) * 1000,
                                   model_version=version, ab_bucket=bucket, pred=overall)
        except Exception:
            pass
        return report

    def _explain(self, weak: list[ConceptMastery], error_profile: dict[str, float],
                 overall: float, n: int) -> str:
        if n == 0:
            return "暂无作答记录，建议先完成 15 分钟入门诊断测试以建立你的能力画像。"
        err_name = {"concept": "概念误解", "calculation": "计算失误", "misread": "审题失误",
                    "logic": "逻辑/推理", "time": "时间管理"}
        parts = [f"已分析 {n} 条作答，整体掌握度 {overall:.0%}。"]
        if weak:
            top = "、".join(cm.concept_name for cm in weak[:3])
            parts.append(f"最需优先突破：{top}。")
        if error_profile:
            main = max(error_profile, key=error_profile.get)
            parts.append(f"主要失分原因为「{err_name.get(main, main)}」"
                         f"（占比 {error_profile[main]:.0%}），后续将针对性强化。")
        parts.append("推荐题目难度将锁定在你的「最近发展区」，确保每题都跳一跳够得着。")
        return "".join(parts)


# 单例
ENGINE = DiagnosisEngine()
