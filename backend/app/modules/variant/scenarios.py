"""情境库（PRD 4.2）：覆盖科技前沿、社会热点、生产生活等 10 大类。

变式题在「保持数学模型不变」的前提下，用这些情境替换题目背景/已知条件/设问，
使题目贴近高考命题趋势（应用化、真实情境）。抽象题型（如纯导数求极值）可不套情境。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# 10 大类（与高考命题趋势对齐）
SCENARIO_CATEGORIES = [
    "科技前沿", "社会热点", "生产生活", "经济金融", "体育竞技",
    "农业生态", "环境保护", "医疗健康", "教育文化", "交通出行",
]


@dataclass(frozen=True)
class SeqScenario:
    """数列类应用情境：actor 的某项 noun 随 unit 线性增长。"""

    category: str
    actor: str
    noun: str  # 含单位，如 “产量(件)”
    unit: str  # 时间单位：月/年/周/季度


SEQUENCE_SCENARIOS: list[SeqScenario] = [
    SeqScenario("科技前沿", "某AI公司", "日活用户(万)", "月"),
    SeqScenario("社会热点", "某城市", "新能源汽车保有量(万辆)", "年"),
    SeqScenario("生产生活", "某智能工厂", "产量(件)", "月"),
    SeqScenario("经济金融", "某储户", "年末存款(千元)", "年"),
    SeqScenario("体育竞技", "某马拉松选手", "周训练里程(km)", "周"),
    SeqScenario("农业生态", "某生态农场", "粮食产量(吨)", "年"),
    SeqScenario("环境保护", "某城区", "新增绿化面积(公顷)", "年"),
    SeqScenario("医疗健康", "某三甲医院", "互联网门诊量(百人次)", "月"),
    SeqScenario("教育文化", "某在线课堂", "注册学员(百人)", "月"),
    SeqScenario("交通出行", "某地铁新线", "日均客流(万人次)", "季度"),
]


@dataclass(frozen=True)
class ProbScenario:
    """古典概型情境：从一批含 good/bad 两类的对象中抽取。"""

    category: str
    container: str
    good: str
    bad: str
    action: str


PROB_SCENARIOS: list[ProbScenario] = [
    ProbScenario("生产生活", "一箱零件", "合格品", "次品", "任取2件"),
    ProbScenario("医疗健康", "一组试剂", "有效", "失效", "随机取2支"),
    ProbScenario("农业生态", "一袋种子", "饱满粒", "瘪粒", "任取2粒"),
    ProbScenario("教育文化", "一组答题卡", "优秀", "待提升", "随机抽2份"),
    ProbScenario("科技前沿", "一批芯片", "良品", "瑕疵品", "任取2片"),
]


@dataclass(frozen=True)
class IneqScenario:
    """基本不等式情境：某正变量与其反比项之和取最小。"""

    category: str
    var_desc: str  # x 的现实含义
    sum_desc: str  # x + k/x 的现实含义


INEQ_SCENARIOS: list[IneqScenario] = [
    IneqScenario("生产生活", "矩形场地一边长 x(米)", "围栏总长相关量 x + {k}/x"),
    IneqScenario("经济金融", "投入资金 x(万元)", "综合成本 x + {k}/x"),
    IneqScenario("环境保护", "处理单元数 x", "单位能耗 x + {k}/x"),
    IneqScenario("交通出行", "发车间隔 x(分钟)", "综合等待指标 x + {k}/x"),
]


def pick(pool: list, rng: random.Random, category: str | None = None):
    cand = [s for s in pool if category is None or s.category == category] or pool
    return rng.choice(cand)
