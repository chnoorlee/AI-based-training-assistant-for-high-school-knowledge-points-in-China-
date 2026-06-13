"""参数化变式题模板（PRD 4.2 的核心）。

每个模板 = 固定考点/数学模型 + 可采样参数 + **符号求解器**。答案由求解器算出而非生成，
从根上保证数学正确性；改变参数/情境/设问即得无穷变式。知识点对齐已有图谱，
生成题可直接回流到苏格拉底解题、认知诊断与推荐。
"""
from __future__ import annotations

import math
import random
import re
from fractions import Fraction
from typing import Optional

from app.modules.variant.scenarios import (
    INEQ_SCENARIOS, PROB_SCENARIOS, SEQUENCE_SCENARIOS, pick,
)

# ── 数学工具 ────────────────────────────────────────────────


def simplify_sqrt(n: int) -> str:
    """√n 化简为最简根式字符串：49→'7'，18→'3√2'，7→'√7'。"""
    if n == 0:
        return "0"
    out, k, f = 1, n, 2
    while f * f <= k:
        while k % (f * f) == 0:
            out *= f
            k //= f * f
        f += 1
    if k == 1:
        return str(out)
    return f"√{k}" if out == 1 else f"{out}√{k}"


def mul2_sqrt(s: str) -> str:
    """把根式字符串整体乘 2：'3'→'6'，'√6'→'2√6'，'2√2'→'4√2'。"""
    if s.isdigit():
        return str(2 * int(s))
    if s.startswith("√"):
        return "2" + s
    m = re.match(r"(\d+)√(\d+)", s)
    return f"{2 * int(m.group(1))}√{m.group(2)}"


def frac_str(fr: Fraction) -> str:
    return str(fr.numerator) if fr.denominator == 1 else f"{fr.numerator}/{fr.denominator}"


def _coef(c: Fraction, sym: str) -> str:
    if c == 0:
        return ""
    if c.denominator == 1:
        v = c.numerator
        if v == 1:
            return f"+{sym}"
        if v == -1:
            return f"-{sym}"
        return f"+{v}{sym}" if v > 0 else f"-{abs(v)}{sym}"
    sign = "+" if c > 0 else "-"
    return f"{sign}({abs(c.numerator)}/{c.denominator}){sym}"


def poly2_str(c2: Fraction, c1: Fraction) -> str:
    s = _coef(c2, "n²") + _coef(c1, "n")
    return (s[1:] if s.startswith("+") else s) or "0"


# ── 模板基类 ────────────────────────────────────────────────


class VariantTemplate:
    id: str = ""
    concept_ids: list[str] = []
    base_difficulty: float = 0.5
    base_discrimination: float = 0.5
    ability: str = "apply"
    ptype: str = "solution"
    scenario_kind: Optional[str] = None  # None | "sequence" | "prob" | "ineq"

    def sample_params(self, rng: random.Random) -> dict:
        raise NotImplementedError

    def build(self, params: dict, scenario, rng: random.Random) -> dict:
        raise NotImplementedError


# ── T1 三次函数极值（抽象，导数）──────────────────────────────
class DerivExtremumTemplate(VariantTemplate):
    id = "T_DERIV_EXTREMUM"
    concept_ids = ["MATH_DERIV_MONO", "MATH_DERIV_EXTREME"]
    base_difficulty = 0.5
    base_discrimination = 0.6
    ability = "analyze"

    def sample_params(self, rng):
        k = rng.choice([1, 2, 3, 4, 5])
        return {"k": k, "b": 3 * k * k}

    def build(self, params, scenario, rng):
        k, b = params["k"], params["b"]
        maxv, minv = 2 * k ** 3, -2 * k ** 3
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": f"已知函数 f(x)=x³-{b}x，求 f(x) 的单调区间与极值。",
            "options": {},
            "answer": (f"增区间 (-∞,-{k}) 和 ({k},+∞)，减区间 (-{k},{k})；"
                       f"极大值 f(-{k})={maxv}，极小值 f({k})={minv}。"),
            "solution_steps": [
                f"求导：f′(x)=3x²-{b}=3(x-{k})(x+{k})。",
                f"令 f′(x)=0，得 x=±{k}，将定义域分为三段。",
                f"判号：x<-{k} 时 f′>0（增）；-{k}<x<{k} 时 f′<0（减）；x>{k} 时 f′>0（增）。",
                f"故增区间 (-∞,-{k}) 与 ({k},+∞)，减区间 (-{k},{k})。",
                f"极大值 f(-{k})={maxv}，极小值 f({k})={minv}。"],
            "socratic_questions": [
                "求单调区间，第一步通常对函数做什么运算？",
                "解出 f′(x)=0 的根后，它们把定义域分成几段？每段如何取符号？",
                "极大值还是极小值，由 f′ 的符号如何变化来判断？"],
            "common_errors": ["把极值点 x 当作极值", "区间开闭写错", "导数符号判断颠倒"],
        }


# ── T2 等差数列前n项和（应用，套情境）─────────────────────────
class ArithSumTemplate(VariantTemplate):
    id = "T_ARITH_SUM"
    concept_ids = ["MATH_SEQ_ARITH", "MATH_SEQ_SUM"]
    base_difficulty = 0.4
    base_discrimination = 0.5
    ability = "apply"
    scenario_kind = "sequence"

    def sample_params(self, rng):
        return {"a1": rng.randint(1, 6), "d": rng.randint(2, 5)}

    def build(self, params, scenario, rng):
        a1, d = params["a1"], params["d"]
        c2, c1 = Fraction(d, 2), Fraction(2 * a1 - d, 2)
        expanded = poly2_str(c2, c1)
        if scenario:
            stem = (f"{scenario.actor}计划逐{scenario.unit}提升{scenario.noun}："
                    f"第 1 {scenario.unit}为 {a1}，此后每{scenario.unit}比上一{scenario.unit}"
                    f"增加 {d}。求前 n {scenario.unit}累计的{scenario.noun}（用 n 表示）。")
        else:
            stem = f"等差数列 {{aₙ}} 中，a₁={a1}，公差 d={d}，求前 n 项和 Sₙ。"
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": stem, "options": {},
            "answer": f"Sₙ = {expanded}（即 n(2×{a1}+(n-1)×{d})/2）。",
            "solution_steps": [
                f"建立等差模型：首项 a₁={a1}，公差 d={d}，aₙ=a₁+(n-1)d={a1}+(n-1)×{d}。",
                "前 n 项和 Sₙ=n(a₁+aₙ)/2=n(2a₁+(n-1)d)/2。",
                f"代入并化简：Sₙ=n(2×{a1}+(n-1)×{d})/2={expanded}。"],
            "socratic_questions": [
                "把这个增长抽象成数列，它是等差还是等比？首项和公差各是多少？",
                "等差数列前 n 项和有哪两个公式？这里哪个更方便？",
                "代入 a₁ 和 d 后，能否化简成关于 n 的简洁表达式？"],
            "common_errors": ["通项 a₁+(n-1)d 写错", "套错求和公式", "化简时系数算错"],
        }


# ── T3 余弦定理解三角形（抽象）───────────────────────────────
class CosineLawTemplate(VariantTemplate):
    id = "T_COSINE_LAW"
    concept_ids = ["MATH_SOLVE_TRIANGLE"]
    base_difficulty = 0.45
    base_discrimination = 0.55
    ability = "apply"
    _COS = {60: "ac", 90: "0", 120: "+ac"}

    def sample_params(self, rng):
        a, c = rng.randint(2, 9), rng.randint(2, 9)
        B = rng.choice([60, 90, 120])
        return {"a": a, "c": c, "B": B}

    def build(self, params, scenario, rng):
        a, c, B = params["a"], params["c"], params["B"]
        if B == 60:
            b2 = a * a + c * c - a * c
        elif B == 90:
            b2 = a * a + c * c
        else:
            b2 = a * a + c * c + a * c
        b_str = simplify_sqrt(b2)
        cos_disp = {60: "½", 90: "0", 120: "(-½)"}[B]
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": f"在 △ABC 中，已知 a={a}，c={c}，B={B}°，求边 b。",
            "options": {},
            "answer": f"b={b_str}。",
            "solution_steps": [
                "已知两边及其夹角，求第三边，用余弦定理：b²=a²+c²-2ac·cosB。",
                f"代入：b²={a}²+{c}²-2×{a}×{c}×{cos_disp}={b2}。",
                f"故 b={b_str}。"],
            "socratic_questions": [
                "已知两边和它们的夹角求第三边，应该用正弦定理还是余弦定理？",
                "余弦定理 b²=a²+c²-2ac·cosB 你能写出来吗？",
                f"cos{B}° 的值是多少？代入算一算。"],
            "common_errors": ["余弦定理符号写错", f"cos{B}° 记错", "开方时未化简根式"],
        }


# ── T4 基本不等式最小值（选择，套情境）───────────────────────
class AmGmMinTemplate(VariantTemplate):
    id = "T_AMGM_MIN"
    concept_ids = ["MATH_INEQ"]
    base_difficulty = 0.4
    base_discrimination = 0.5
    ability = "apply"
    ptype = "choice"
    scenario_kind = "ineq"

    def sample_params(self, rng):
        # 排除 k=1,4（会导致干扰项与正确项重复）
        return {"k": rng.choice([2, 3, 5, 6, 7, 8, 9, 10, 12, 15, 18])}

    def build(self, params, scenario, rng):
        k = params["k"]
        sqk = simplify_sqrt(k)
        min_str = mul2_sqrt(sqk)  # 2√k
        if scenario:
            stem = (f"{scenario.var_desc}（x>0），综合指标为 "
                    f"{scenario.sum_desc.format(k=k)}，则该指标的最小值为（　）")
        else:
            stem = f"已知 x>0，则 x+{k}/x 的最小值为（　）"
        distractors = [sqk, str(k), "不存在"]
        opts_vals = [min_str] + [d for d in distractors if d != min_str][:3]
        rng.shuffle(opts_vals)
        letters = ["A", "B", "C", "D"]
        options = {letters[i]: opts_vals[i] for i in range(len(opts_vals))}
        answer = next(L for L, v in options.items() if v == min_str)
        return {
            "type": "choice", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": stem, "options": options, "answer": answer,
            "solution_steps": [
                "x>0，由基本不等式 a+b≥2√(ab)（a,b>0）。",
                f"x+{k}/x≥2√(x·{k}/x)=2√{k}={min_str}，当且仅当 x={sqk} 取等。",
                f"故最小值为 {min_str}，选 {answer}。"],
            "socratic_questions": [
                "基本不等式 a+b≥2√(ab) 成立的前提是什么？这里满足吗？",
                "把 x 与 k/x 看作两个数，它们的乘积是不是定值？这一步为何关键？",
                "取等号的条件是什么？解出的 x 在定义域内吗？"],
            "common_errors": ["忘记乘 2（漏掉 2√k 的系数）", "不验证取等条件", "忽略 x>0 前提"],
        }


# ── T5 古典概型（应用，套情境）──────────────────────────────
class ClassicProbTemplate(VariantTemplate):
    id = "T_CLASSIC_PROB"
    concept_ids = ["MATH_PROB"]
    base_difficulty = 0.4
    base_discrimination = 0.5
    ability = "apply"
    scenario_kind = "prob"

    def sample_params(self, rng):
        return {"good": rng.randint(2, 5), "bad": rng.randint(1, 4)}

    def build(self, params, scenario, rng):
        g, b = params["good"], params["bad"]
        n = g + b
        total = math.comb(n, 2)
        fav = g * b
        p = Fraction(fav, total)
        if scenario:
            stem = (f"{scenario.container}中有 {g} 个{scenario.good}和 {b} 个{scenario.bad}，"
                    f"{scenario.action}，求恰好取到 1 个{scenario.good}和 1 个{scenario.bad}的概率。")
            gname, bname = scenario.good, scenario.bad
        else:
            stem = (f"袋中有 {g} 个红球、{b} 个白球，从中任取 2 个，"
                    f"求恰好取到 1 红 1 白的概率。")
            gname, bname = "红球", "白球"
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": stem, "options": {}, "answer": f"{frac_str(p)}。",
            "solution_steps": [
                f"古典概型，样本空间总数 C({n},2)={total}。",
                f"有利结果：C({g},1)·C({b},1)={g}×{b}={fav}。",
                f"概率 P={fav}/{total}={frac_str(p)}。"],
            "socratic_questions": [
                "这是古典概型吗？任取 2 个的所有等可能结果共有多少种？",
                f"「恰好 1 个{gname} 1 个{bname}」如何用组合数计数？",
                "有利结果数除以总数，得到的概率是多少？"],
            "common_errors": ["分母误用排列 A(n,2)", "忘记两类取法相乘", "未把概率约分"],
        }


# ── T6 椭圆离心率（抽象）────────────────────────────────────
class EllipseEccentricityTemplate(VariantTemplate):
    id = "T_ELLIPSE_ECC"
    concept_ids = ["MATH_CONIC"]
    base_difficulty = 0.4
    base_discrimination = 0.5
    ability = "apply"
    # 精选 (A,B,e_str)，保证离心率为最简形式
    _PAIRS = [(4, 1, "√3/2"), (4, 3, "1/2"), (9, 5, "2/3"), (16, 7, "3/4"),
              (25, 9, "4/5"), (25, 16, "3/5"), (5, 4, "√5/5"), (2, 1, "√2/2")]

    def sample_params(self, rng):
        A, B, e = rng.choice(self._PAIRS)
        return {"A": A, "B": B, "e": e}

    def build(self, params, scenario, rng):
        A, B, e = params["A"], params["B"], params["e"]
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": f"求椭圆 x²/{A} + y²/{B} = 1 的离心率。",
            "options": {}, "answer": f"e={e}。",
            "solution_steps": [
                f"a²={A}，b²={B}（a²>b²，焦点在 x 轴）。",
                f"c²=a²-b²={A}-{B}={A - B}，c=√{A - B}。",
                f"离心率 e=c/a=√{A - B}/√{A}={e}。"],
            "socratic_questions": [
                "椭圆标准方程里 a² 和 b² 哪个大？焦点在哪条轴上？",
                "a、b、c 满足什么关系？（注意与双曲线不同）",
                "离心率 e 的定义是什么？"],
            "common_errors": ["用了双曲线的 c²=a²+b²", "a、b 取反导致 e>1", "未化简离心率"],
        }


# ══ 理综/科学模板（物理/化学/生物，符号求解保证正确）═══════════════
class KinematicsTemplate(VariantTemplate):
    id = "T_PHY_KINEMATICS"
    concept_ids = ["PHY_KINEMATICS"]
    base_difficulty = 0.35
    base_discrimination = 0.5
    ability = "apply"

    def sample_params(self, rng):
        return {"v0": rng.randint(1, 6), "a": rng.randint(1, 5), "t": rng.randint(2, 6)}

    def build(self, params, scenario, rng):
        v0, a, t = params["v0"], params["a"], params["t"]
        v = v0 + a * t
        s = v0 * t + 0.5 * a * t * t
        s_str = str(int(s)) if s == int(s) else str(s)
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": f"物体做匀加速直线运动，初速度 v₀={v0} m/s，加速度 a={a} m/s²，"
                    f"求第 {t} s 末的速度 v 与这 {t} s 内的位移 s。",
            "options": {}, "answer": f"v={v} m/s，s={s_str} m。",
            "solution_steps": [f"速度公式 v=v₀+at={v0}+{a}×{t}={v} m/s。",
                               f"位移公式 s=v₀t+½at²={v0}×{t}+½×{a}×{t}²={s_str} m。"],
            "socratic_questions": ["匀变速直线运动的速度公式和位移公式分别是什么？",
                                   "已知 v₀、a、t，先求哪个量更直接？", "代入时单位是否统一？"],
            "common_errors": ["位移公式漏掉 ½", "把 a 当成 v", "时间平方算错"],
        }


class OhmLawTemplate(VariantTemplate):
    id = "T_PHY_OHM"
    concept_ids = ["PHY_CIRCUIT"]
    base_difficulty = 0.45
    base_discrimination = 0.55
    ability = "apply"

    def sample_params(self, rng):
        return {"E": rng.choice([4, 6, 8, 9, 12]), "r": rng.randint(1, 3), "R": rng.randint(1, 9)}

    def build(self, params, scenario, rng):
        E, r, R = params["E"], params["r"], params["R"]
        I = Fraction(E, R + r)
        U = I * R
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": f"电源电动势 E={E} V，内阻 r={r} Ω，外接电阻 R={R} Ω，"
                    f"求电路电流 I 和路端电压 U。",
            "options": {}, "answer": f"I={frac_str(I)} A，U={frac_str(U)} V。",
            "solution_steps": [f"闭合电路欧姆定律 I=E/(R+r)={E}/({R}+{r})={frac_str(I)} A。",
                               f"路端电压 U=IR={frac_str(I)}×{R}={frac_str(U)} V。"],
            "socratic_questions": ["闭合电路欧姆定律 I 等于什么？分母为何是 R+r？",
                                   "求出电流后路端电压怎么算？", "U 与电动势 E 的关系是什么？"],
            "common_errors": ["分母漏掉内阻 r", "路端电压当成电动势", "U=IR 与 U=E-Ir 混用出错"],
        }


class MoleTemplate(VariantTemplate):
    id = "T_CHEM_MOLE"
    concept_ids = ["CHEM_MOLE"]
    base_difficulty = 0.3
    base_discrimination = 0.45
    ability = "apply"
    _SUB = [("水(H₂O)", 18), ("二氧化碳(CO₂)", 44), ("氧气(O₂)", 32),
            ("氢氧化钠(NaOH)", 40), ("碳酸钙(CaCO₃)", 100)]

    def sample_params(self, rng):
        name, M = rng.choice(self._SUB)
        return {"name": name, "M": M, "k": rng.randint(1, 4)}

    def build(self, params, scenario, rng):
        name, M, k = params["name"], params["M"], params["k"]
        m = k * M
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": f"{m} g {name}（摩尔质量 M={M} g/mol）的物质的量 n 为多少？",
            "options": {}, "answer": f"{k} mol。",
            "solution_steps": [f"物质的量 n=m/M={m}/{M}={k} mol。"],
            "socratic_questions": ["物质的量、质量、摩尔质量的关系式是什么？",
                                   "摩尔质量在哪里给出了？", "代入计算结果是多少？"],
            "common_errors": ["n=M/m 写反", "摩尔质量记错", "单位忘记 mol"],
        }


class GeneticsTemplate(VariantTemplate):
    id = "T_BIO_GENETICS"
    concept_ids = ["BIO_GENETICS"]
    base_difficulty = 0.4
    base_discrimination = 0.5
    ability = "apply"
    _CROSS = {"Aa×Aa": ((0.5, 0.5), (0.5, 0.5)), "Aa×aa": ((0.5, 0.5), (0.0, 1.0)),
              "AA×Aa": ((1.0, 0.0), (0.5, 0.5))}
    _Q = ["显性性状（A_）", "隐性性状（aa）", "纯合子（AA或aa）", "杂合子（Aa）"]

    def sample_params(self, rng):
        return {"cross": rng.choice(list(self._CROSS.keys())), "q": rng.choice(self._Q)}

    def build(self, params, scenario, rng):
        cross, q = params["cross"], params["q"]
        (pA1, pa1), (pA2, pa2) = self._CROSS[cross]
        AA = Fraction(pA1).limit_denominator() * Fraction(pA2).limit_denominator()
        aa = Fraction(pa1).limit_denominator() * Fraction(pa2).limit_denominator()
        Aa = 1 - AA - aa
        prob = {"显性性状（A_）": AA + Aa, "隐性性状（aa）": aa,
                "纯合子（AA或aa）": AA + aa, "杂合子（Aa）": Aa}[q]
        return {
            "type": "solution", "concept_ids": self.concept_ids, "ability": self.ability,
            "stem": f"基因型为 {cross} 的两个个体杂交，求其后代表现「{q}」的概率。",
            "options": {}, "answer": f"{frac_str(prob)}。",
            "solution_steps": [
                f"由 {cross} 推后代基因型概率：AA={frac_str(AA)}，Aa={frac_str(Aa)}，aa={frac_str(aa)}。",
                f"「{q}」对应概率={frac_str(prob)}。"],
            "socratic_questions": [f"{cross} 后代的基因型有哪几种？各占多少？",
                                   f"「{q}」包含哪些基因型？", "把对应概率相加即可。"],
            "common_errors": ["显隐概率混淆", "基因型比例记错", "纯合/杂合判断反"],
        }


TEMPLATES: dict[str, VariantTemplate] = {
    t.id: t for t in [
        DerivExtremumTemplate(), ArithSumTemplate(), CosineLawTemplate(),
        AmGmMinTemplate(), ClassicProbTemplate(), EllipseEccentricityTemplate(),
        KinematicsTemplate(), OhmLawTemplate(), MoleTemplate(), GeneticsTemplate(),
    ]
}

# 知识点 → 可用模板（用于按种子题/考点选模板）
CONCEPT_TO_TEMPLATES: dict[str, list[str]] = {}
for _t in TEMPLATES.values():
    for _c in _t.concept_ids:
        CONCEPT_TO_TEMPLATES.setdefault(_c, []).append(_t.id)


def scenario_pool(kind: Optional[str]):
    return {"sequence": SEQUENCE_SCENARIOS, "prob": PROB_SCENARIOS,
            "ineq": INEQ_SCENARIOS}.get(kind)


def pick_scenario(kind: Optional[str], rng: random.Random, category: Optional[str] = None):
    pool = scenario_pool(kind)
    return pick(pool, rng, category) if pool else None
