"""高考卷面结构蓝图：各科按真实卷面拆成区块（题型 + 难度档 + 分值 + 建议用时 + 典型丢分原因）。

用于把"应试丢分"下钻到题型级（选择易/选择压轴/填空/中档大题/压轴最后一问），
据此开出精准的限时训练。分值/用时按主流卷面估计，可按地区校准。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    id: str
    name: str
    qtype: str  # choice / blank / solution
    points: float  # 该区块总分
    tier: str  # 易 / 中 / 难 / 压轴
    rec_minutes: int  # 建议用时
    cause: str  # 该区块典型丢分原因


PAPER_BLUEPRINT: dict[str, list[Section]] = {
    "math": [  # 满分 150
        Section("m_ch_easy", "选择题(基础)", "choice", 30, "易", 18, "审题/手滑"),
        Section("m_ch_hard", "选择题(压轴)", "choice", 10, "难", 12, "技巧/时间不足"),
        Section("m_blank", "填空题", "blank", 20, "中", 20, "计算/审题"),
        Section("m_solve_mid", "解答题(中档)", "solution", 46, "中", 50, "计算/步骤规范"),
        Section("m_solve_hard", "解答题(压轴·最后一问)", "solution", 44, "压轴", 50, "难度/时间/不敢下手"),
    ],
    "physics": [  # ~110
        Section("p_choice", "选择题", "choice", 30, "中", 25, "审题/概念混淆"),
        Section("p_exp", "实验题", "solution", 18, "中", 18, "实验操作/读数/有效数字"),
        Section("p_calc_mid", "计算题(中档)", "solution", 30, "中", 30, "受力分析/公式代入"),
        Section("p_calc_hard", "计算题(压轴)", "solution", 32, "压轴", 35, "多过程/时间/不敢下手"),
    ],
    "chemistry": [  # ~100
        Section("c_choice", "选择题", "choice", 24, "中", 20, "概念/审题"),
        Section("c_exp", "实验/工艺流程", "solution", 36, "中", 35, "信息提取/规范表述"),
        Section("c_hard", "反应原理(压轴)", "solution", 40, "压轴", 40, "计算/图像/时间"),
    ],
    "biology": [  # ~90
        Section("b_choice", "选择题", "choice", 36, "中", 25, "概念/审题"),
        Section("b_short", "非选择(中档)", "solution", 30, "中", 30, "术语/表述规范"),
        Section("b_genetics", "遗传压轴", "solution", 24, "压轴", 30, "推断/概率/时间"),
    ],
}


def sections_of(subject: str) -> list[Section]:
    return PAPER_BLUEPRINT.get(subject, [])


def section(subject: str, section_id: str) -> Section | None:
    for s in sections_of(subject):
        if s.id == section_id:
            return s
    return None
