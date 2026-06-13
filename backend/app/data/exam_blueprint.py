"""高考考点分值蓝图：各学科各模块在高考中的大致分值占比。

用于"提分性价比"计算——高分值 + 低掌握 + 易提分 的考点最该优先补。
数值为各模块典型分值（按主流卷面估计，可按地区/年份校准），仅作相对排序与预计提分的标尺。
"""
from __future__ import annotations

from app.data.knowledge_graph import KG

# subject -> {module: 分值}
EXAM_BLUEPRINT: dict[str, dict[str, float]] = {
    "math": {  # 满分 150
        "预备知识": 3, "函数与导数": 30, "三角函数": 16, "平面向量": 10, "数列": 16,
        "立体几何": 17, "解析几何": 22, "概率统计": 16, "不等式": 15, "复数": 5,
    },
    "physics": {  # 理综物理 ~110
        "运动学": 18, "力学": 22, "能量": 18, "振动与波": 12, "电学": 20, "电磁学": 20,
    },
    "chemistry": {  # 理综化学 ~100
        "基本概念": 16, "反应原理": 34, "物质结构": 18, "有机化学": 18, "电化学": 14,
    },
    "biology": {  # 理综生物 ~90
        "分子与细胞": 20, "代谢": 22, "遗传与进化": 30, "稳态与环境": 18,
    },
}

_DEFAULT_MODULE_PTS = 6.0


def module_points(subject: str, module: str) -> float:
    return EXAM_BLUEPRINT.get(subject, {}).get(module, _DEFAULT_MODULE_PTS)


def concept_weight(concept_id: str) -> float:
    """知识点高考权重（分）：所在模块分值在该模块知识点间均摊。"""
    c = KG.get(concept_id)
    if c is None:
        return 1.0
    subj, mod = c.subject.value, c.module
    peers = [x for x in KG.concepts_in_module(mod) if KG.subject_of(x) == subj] or [concept_id]
    return round(module_points(subj, mod) / len(peers), 2)


def subject_total(subject: str) -> float:
    return float(sum(EXAM_BLUEPRINT.get(subject, {}).values()))
