"""变式题质量控制（PRD 4.2 质量控制三件套 + 内容安全）。

自动门（机审）：① 规则校验（超纲/选项/答案）② 难度系数与区分度预测
③ 去重 + 版权相似度（与受版权语料相似度须 ≤0.30）④ 内容安全。
全部通过 → 进入人工审核队列（PENDING）；任一不过 → AUTO_REJECTED。
人工审核（教师）由 review 模块承接，是入库前的最后一关。
"""
from __future__ import annotations

import re

from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.schemas import VariantQualityReport

# 受版权保护语料：生产加载真题/教辅原文；MVP 默认空（可注入以演示版权门）
PROTECTED_CORPUS: list[str] = []

# 内容安全：超纲/价值观/无关 关键词（示意，生产用分类模型）
_BANNED = ["微积分中值定理", "洛必达", "政治敏感", "赌博", "暴力"]
_SUPERSCRIPT_OK = True


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _trigrams(s: str) -> set[str]:
    s = _clean(s)
    return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}


def text_similarity(a: str, b: str) -> float:
    """字符三元组 Jaccard 相似度（0~1）。"""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def predict_difficulty(fields: dict, base_difficulty: float,
                       base_discrimination: float) -> tuple[float, float]:
    """特征法难度/区分度预测（生产替换为标定模型）。

    特征：解题步数、能力层级、题型、题面数值量级。
    """
    d = base_difficulty
    d += 0.03 * (len(fields.get("solution_steps", [])) - 3)
    d += {"analyze": 0.10, "synthesize": 0.15, "create": 0.18,
          "apply": 0.0, "understand": -0.05, "memory": -0.08}.get(fields.get("ability"), 0.0)
    if fields.get("type") == "choice":
        d -= 0.05  # 选择题相对容易
    nums = [int(x) for x in re.findall(r"\d+", fields.get("stem", ""))]
    if nums and max(nums) >= 20:
        d += 0.04  # 数值量级偏大略增难度
    d = max(0.1, min(0.95, d))
    disc = max(0.2, min(0.9, base_discrimination + (0.05 if d > 0.6 else 0.0)))
    return round(d, 3), round(disc, 3)


def rule_check(fields: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    # 超纲：知识点必须在图谱内
    for c in fields.get("concept_ids", []):
        if KG.get(c) is None:
            issues.append(f"超纲/未知知识点：{c}")
    if not fields.get("stem", "").strip():
        issues.append("题干为空")
    ans = str(fields.get("answer", ""))
    if not ans.strip() or "None" in ans or "nan" in ans.lower():
        issues.append("答案缺失或非法")
    if fields.get("type") == "choice":
        opts = fields.get("options", {})
        if len(opts) < 3:
            issues.append("选择题选项少于 3 个")
        if len(set(opts.values())) != len(opts):
            issues.append("选择题存在重复选项")
        if fields.get("answer") not in opts:
            issues.append("正确答案不在选项中")
    return (len(issues) == 0), issues


def content_safety(fields: dict) -> tuple[bool, list[str]]:
    text = (fields.get("stem", "") + " " + str(fields.get("answer", "")))
    hits = [w for w in _BANNED if w in text]
    return (len(hits) == 0), ([f"命中敏感/超纲词：{w}" for w in hits])


def dedup_similarity(stem: str, batch_stems: list[str]) -> float:
    """与题库及同批已生成题的最大文本相似度（防重复/防资源浪费）。"""
    sims = [text_similarity(stem, p.stem) for p in BANK.all()]
    sims += [text_similarity(stem, s) for s in batch_stems]
    return round(max(sims) if sims else 0.0, 3)


def copyright_similarity(stem: str, corpus: list[str] | None = None) -> float:
    """与受版权保护语料的最大相似度（须 ≤0.30，IP 合规）。"""
    corpus = PROTECTED_CORPUS if corpus is None else corpus
    sims = [text_similarity(stem, c) for c in corpus]
    return round(max(sims) if sims else 0.0, 3)


def run_quality(fields: dict, base_difficulty: float, base_discrimination: float,
                batch_stems: list[str], protected_corpus: list[str] | None = None,
                dedup_threshold: float = 0.98, copyright_threshold: float = 0.30
                ) -> VariantQualityReport:
    # 注：变式题与其种子题"结构相似"是设计使然，去重只拦"几乎完全雷同"(>0.98)；
    # 防止复制受版权材料由独立的 copyright_similarity(≤0.30) 负责。
    rule_ok, rule_issues = rule_check(fields)
    safe, safety_issues = content_safety(fields)
    diff, disc = predict_difficulty(fields, base_difficulty, base_discrimination)
    dedup = dedup_similarity(fields.get("stem", ""), batch_stems)
    cpy = copyright_similarity(fields.get("stem", ""), protected_corpus)

    notes: list[str] = []
    if dedup > dedup_threshold:
        notes.append(f"与既有题目过于相似（{dedup:.2f}>{dedup_threshold}），疑似重复")
    if cpy > copyright_threshold:
        notes.append(f"版权相似度过高（{cpy:.2f}>{copyright_threshold}），涉嫌复制受版权材料")

    auto = rule_ok and safe and dedup <= dedup_threshold and cpy <= copyright_threshold
    return VariantQualityReport(
        rule_passed=rule_ok, rule_issues=rule_issues,
        predicted_difficulty=diff, predicted_discrimination=disc,
        dedup_similarity=dedup, copyright_similarity=cpy,
        content_safe=safe, safety_issues=safety_issues,
        auto_passed=auto, notes=notes)
