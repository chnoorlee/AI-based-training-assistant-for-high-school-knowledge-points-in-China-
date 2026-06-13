"""★ 全链路合规闸门（PRD 6.1）。

落地三道硬约束：
  1) 高考熔断：6/7–6/10（含首尾，可配置，Asia/Shanghai）自动关闭
     解析/解题/作文/生成类功能，仅保留错题本、知识点复习、诊断报告查看。
  2) 防沉迷：单日累计用量 ≤ 3 小时；23:00–次日 06:00 锁定。
  3) 功能门控：受限时明确告知原因与「仍可使用的功能」，而非粗暴报错。

设计为纯函数：给定 (feature, 当日已用分钟, 当前时间) 即可判定，便于单元测试与审计。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from app.core.config import settings
from app.schemas import ComplianceStatus

# 需要在高考期间熔断的功能（解析/解题/作文/推题等"做新题"类）
BLACKOUT_FEATURES = {"solve", "parse", "essay_grade", "generate", "variant",
                     "subjective_grade", "recommend", "cold_start"}
# 熔断期间仍开放的功能
ALWAYS_ALLOWED: list[str] = ["wrongbook", "review", "report", "diagnosis_view"]


def _in_gaokao_window(d: date) -> bool:
    return settings.gaokao_blackout_start <= d <= settings.gaokao_blackout_end


def check_gaokao_blackout(feature: str, now: datetime) -> Optional[ComplianceStatus]:
    """高考熔断。命中返回拒绝状态，否则 None。"""
    if feature in ALWAYS_ALLOWED:
        return None
    if not _in_gaokao_window(now.date()):
        return None
    if feature in BLACKOUT_FEATURES:
        return ComplianceStatus(
            allowed=False, feature=feature, code="gaokao_blackout",
            reason=(f"高考期间（{settings.gaokao_blackout_start}~{settings.gaokao_blackout_end}）"
                    "已依规熔断解析/解题/作文等功能。祝你考试顺利！可继续使用错题本与知识点复习。"),
            allowed_features=ALWAYS_ALLOWED)
    return None


def check_anti_addiction(now: datetime, used_minutes_today: float) -> Optional[ComplianceStatus]:
    """防沉迷：夜间锁定 + 单日时长上限。命中返回拒绝状态，否则 None。"""
    h = now.hour
    start, end = settings.night_lock_start_hour, settings.night_lock_end_hour
    # 跨零点区间：23:00–06:00 → h>=23 或 h<6
    night = (h >= start) or (h < end) if start > end else (start <= h < end)
    if night:
        # 计算到解锁还有多少分钟
        if h >= start:
            mins = (24 - h) * 60 - now.minute + end * 60
        else:
            mins = (end - h) * 60 - now.minute
        return ComplianceStatus(
            allowed=False, feature="*", code="night_lock",
            reason=f"为保障休息，{start}:00–次日 {end:02d}:00 暂停使用，请早点休息。",
            retry_after_minutes=max(1, mins), allowed_features=[])
    if used_minutes_today >= settings.daily_usage_limit_minutes:
        return ComplianceStatus(
            allowed=False, feature="*", code="daily_limit",
            reason=(f"今日已学习 {int(used_minutes_today)} 分钟，达到 "
                    f"{settings.daily_usage_limit_minutes} 分钟上限。劳逸结合，明天继续加油！"),
            retry_after_minutes=None, allowed_features=ALWAYS_ALLOWED)
    return None


def check(feature: str, used_minutes_today: float = 0.0,
          now: Optional[datetime] = None, is_minor_verified: bool = True) -> ComplianceStatus:
    """统一合规判定。优先级：高考熔断 > 夜间锁定 > 单日上限。"""
    now = now or settings.now()

    blackout = check_gaokao_blackout(feature, now)
    if blackout is not None:
        return blackout

    # 防沉迷仅约束"学习/做题"类功能；报告查看等放行
    if feature not in ALWAYS_ALLOWED:
        addiction = check_anti_addiction(now, used_minutes_today)
        if addiction is not None:
            addiction.feature = feature
            return addiction

    return ComplianceStatus(allowed=True, feature=feature, code="ok")
