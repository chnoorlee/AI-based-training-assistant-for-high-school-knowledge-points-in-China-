"""合规闸门单测：高考熔断 / 夜间锁定 / 单日上限 / 正常放行。"""
from datetime import datetime

from app.core import compliance
from app.core.config import settings


def at(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=settings.tz)


def test_gaokao_blackout_blocks_solve():
    s = compliance.check("solve", used_minutes_today=0, now=at(2026, 6, 7))
    assert not s.allowed and s.code == "gaokao_blackout"
    assert "wrongbook" in s.allowed_features  # 仍开放错题本


def test_gaokao_blackout_allows_wrongbook_and_review():
    assert compliance.check("wrongbook", now=at(2026, 6, 8)).allowed
    assert compliance.check("review", now=at(2026, 6, 9)).allowed
    assert compliance.check("report", now=at(2026, 6, 10)).allowed


def test_gaokao_blackout_blocks_recommend_and_parse():
    assert not compliance.check("recommend", now=at(2026, 6, 7)).allowed
    assert not compliance.check("parse", now=at(2026, 6, 7)).allowed


def test_night_lock():
    s = compliance.check("solve", now=at(2026, 5, 1, 23, 30))
    assert not s.allowed and s.code == "night_lock"
    s2 = compliance.check("solve", now=at(2026, 5, 1, 3, 0))
    assert not s2.allowed and s2.code == "night_lock"


def test_daily_limit():
    s = compliance.check("solve", used_minutes_today=200, now=at(2026, 5, 1, 15))
    assert not s.allowed and s.code == "daily_limit"


def test_allowed_in_normal_window():
    s = compliance.check("solve", used_minutes_today=10, now=at(2026, 5, 1, 15))
    assert s.allowed and s.code == "ok"
