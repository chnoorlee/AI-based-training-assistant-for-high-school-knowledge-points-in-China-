"""作文批改（PRD 5.1）：高考评分标准对齐，内容/表达/发展等级 3 维 × 4 二级维度。

MVP 用「评分细则 + 可度量特征」的透明确定性评分（每个二级维度由一个检测器给 0~1 分率）；
生产把评分核心替换为 10 万阅卷样本微调的教育大模型（接口不变），并按月用最新阅卷数据校准。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.schemas import DimensionScore, EssayGradeResult

# ── 标记词库（议论文常见特征）────────────────────────────────
THESIS = ["我认为", "我以为", "在我看来", "应当", "应该", "正是", "由此可见", "启示",
          "归根结底", "唯有", "只有", "必须", "理应"]
EVIDENCE = ["例如", "比如", "据", "数据", "历史", "事例", "譬如", "正如", "可见", "事实"]
CONNECTIVE = ["首先", "其次", "再次", "然而", "但是", "因此", "所以", "不仅", "而且",
              "总之", "综上", "一方面", "另一方面", "与此同时", "反之"]
ARGUE = ["论点", "论据", "论证", "观点", "证明", "反驳", "立场"]
DIALECTIC = ["辩证", "本质", "根源", "内在", "必然", "矛盾", "客观", "主观", "透过现象",
             "因果", "联系", "发展地看"]
RHETORIC = ["古人云", "诗云", "名言", "正所谓", "曰", "犹如", "宛如", "排比", "比喻"]
BANNED = ["政治敏感", "暴力", "赌博", "色情"]
IDIOM_RE = re.compile(r"[一-鿿]{4}")


def _chars(t: str) -> int:
    return len(re.sub(r"\s", "", t))


def _paragraphs(t: str) -> list[str]:
    return [p for p in re.split(r"\n+", t.strip()) if p.strip()]


def _sentences(t: str) -> list[str]:
    return [s for s in re.split(r"[。！？!?；;]", t) if s.strip()]


def _count(t: str, markers: list[str]) -> int:
    return sum(t.count(m) for m in markers)


def _kw(prompt: str) -> set[str]:
    cjk = re.findall(r"[一-鿿]+", prompt or "")
    grams: set[str] = set()
    for w in cjk:
        grams.update(w[i:i + 2] for i in range(len(w) - 1))
    return grams


# ── 检测器：返回 0~1 分率 ────────────────────────────────────
def d_on_topic(t, prompt):
    kw = _kw(prompt)
    if not kw:
        return 0.75
    hits = sum(1 for g in kw if g in t)
    return max(0.0, min(1.0, hits / max(3, len(kw) * 0.35)))


def d_thesis(t, prompt):
    return min(1.0, _count(t, THESIS) / 2)


def d_substance(t, prompt):
    return 0.5 * min(1.0, _count(t, EVIDENCE) / 3) + 0.5 * min(1.0, _chars(t) / 800)


def d_healthy(t, prompt):
    return 0.2 if any(b in t for b in BANNED) else 1.0


def d_genre(t, prompt):
    return min(1.0, (_count(t, ARGUE) + _count(t, CONNECTIVE)) / 4)


def d_structure(t, prompt):
    n = len(_paragraphs(t))
    base = 1.0 if 4 <= n <= 6 else (0.7 if n in (3, 7) else 0.45)
    conn = min(1.0, _count(t, CONNECTIVE) / 4)
    return base * (0.6 + 0.4 * conn)


def d_fluency(t, prompt):
    ss = _sentences(t)
    if not ss:
        return 0.0
    avg = sum(_chars(s) for s in ss) / len(ss)
    length_ok = 1.0 if 12 <= avg <= 34 else max(0.4, 1 - abs(avg - 23) / 30)
    variety = min(1.0, len(set(re.findall(r"[，。；！？、]", t))) / 4)
    return 0.7 * length_ok + 0.3 * variety


def d_wordcount(t, prompt):
    c = _chars(t)
    if c >= 800:
        return 1.0
    if c >= 600:
        return 0.75
    if c >= 400:
        return 0.5
    return max(0.1, c / 400 * 0.5)


def d_depth(t, prompt):
    return min(1.0, _count(t, DIALECTIC) / 2)


def d_richness(t, prompt):
    return min(1.0, (_count(t, EVIDENCE) + _count(t, RHETORIC)) / 4)


def d_eloquence(t, prompt):
    idioms = len(IDIOM_RE.findall(t))
    return min(1.0, (idioms + _count(t, RHETORIC)) / 6)


def d_creativity(t, prompt):
    c = _chars(t)
    if c < 50:
        return 0.2
    diversity = len(set(re.sub(r"\s", "", t))) / max(1, c)
    return max(0.3, min(1.0, diversity * 1.6))


@dataclass
class Criterion:
    name: str
    max_score: float
    detector: Callable[[str, str], float]


# 高考作文评分细则：3 一级维度 × 4 二级维度，满分 60（各 20）
ESSAY_RUBRIC: dict[str, list[Criterion]] = {
    "内容": [Criterion("切合题意", 5, d_on_topic), Criterion("中心明确", 5, d_thesis),
             Criterion("内容充实", 5, d_substance), Criterion("思想健康", 5, d_healthy)],
    "表达": [Criterion("符合文体", 5, d_genre), Criterion("结构严谨", 5, d_structure),
             Criterion("语言流畅", 5, d_fluency), Criterion("字数规范", 5, d_wordcount)],
    "发展等级": [Criterion("深刻", 5, d_depth), Criterion("丰富", 5, d_richness),
                 Criterion("有文采", 5, d_eloquence), Criterion("有创意", 5, d_creativity)],
}

EXEMPLARS = {
    "议论文": "参考范文《说尺与度》：开门见山立论 → 正反对比论证 → 联系现实 → 辩证收束，"
              "结构清晰、论据典型、收尾升华，可对照其论证层次。",
}


class EssayGrader:
    backend = "rubric-mock"

    def __init__(self, scale: float = 1.0, offset: float = 0.0) -> None:
        # 校准参数（按月用最新阅卷数据拟合，对齐人评分）
        self.scale, self.offset = scale, offset

    def grade(self, prompt: str, text: str, genre: str = "议论文") -> EssayGradeResult:
        dims: list[DimensionScore] = []
        strengths, weaknesses, suggestions = [], [], []
        for dim, crits in ESSAY_RUBRIC.items():
            subs: dict[str, float] = {}
            for c in crits:
                frac = max(0.0, min(1.0, c.detector(text, prompt)))
                sc = round(frac * c.max_score, 1)
                subs[c.name] = sc
                if frac >= 0.85:
                    strengths.append(f"{dim}·{c.name}")
                elif frac < 0.5:
                    weaknesses.append(f"{dim}·{c.name}")
                    suggestions.append(self._suggest(c.name))
            dims.append(DimensionScore(name=dim, max_score=sum(c.max_score for c in crits),
                                       score=round(sum(subs.values()), 1), sub_scores=subs,
                                       comment=self._dim_comment(dim, subs)))
        raw = sum(d.score for d in dims)
        total = max(0.0, min(60.0, round(raw * self.scale + self.offset, 1)))
        return EssayGradeResult(
            total=total, dimensions=dims, strengths=strengths,
            weaknesses=weaknesses or ["整体均衡，无明显短板"],
            suggestions=list(dict.fromkeys(suggestions))[:5] or ["保持，并尝试增加思辨深度与典型论据"],
            exemplar_ref=EXEMPLARS.get(genre, ""), content_safe=d_healthy(text, prompt) >= 1.0,
            grader_backend=self.backend)

    def _suggest(self, crit: str) -> str:
        return {
            "切合题意": "紧扣材料关键词与核心立意，避免偏离话题。",
            "中心明确": "在首段或末段用一句话亮明中心论点。",
            "内容充实": "补充 2-3 个典型论据（事例/数据/名言）支撑论点。",
            "符合文体": "强化论点—论据—论证结构，体现议论文特征。",
            "结构严谨": "分 4-6 段，善用'首先/其次/然而/因此'等过渡。",
            "语言流畅": "控制句长、丰富句式，减少口语化表达。",
            "字数规范": "字数不少于 800 字。",
            "深刻": "尝试辩证分析，揭示现象背后的本质与根源。",
            "丰富": "增加引用、修辞与多角度论据，使内容更饱满。",
            "有文采": "适度运用成语、修辞与名句，提升语言表现力。",
            "有创意": "尝试新颖的角度或结构，避免套路化。",
        }.get(crit, "针对该维度有针对性地修改。")

    def _dim_comment(self, dim: str, subs: dict[str, float]) -> str:
        best = max(subs, key=subs.get)
        worst = min(subs, key=subs.get)
        return f"{dim}维度中「{best}」表现较好，「{worst}」相对薄弱。"


GRADER_ESSAY = EssayGrader()
