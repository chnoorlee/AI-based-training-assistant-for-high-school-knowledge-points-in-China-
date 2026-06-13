"""模考 → 规划 的反馈信号。

把真实模考暴露的「弱科 + 应试丢分(会做却失分) + 退步趋势」转成各科规划加权，
让提分规划把时间更多投向"真实考场上最该补"的科目；同时给出应试缺口供学生看清问题。
"""
from __future__ import annotations


def analyze(book, report, predictor, user_id: str) -> dict[str, dict]:
    """返回 {subject: {actual, raw, full, execution_gap, declining, multiplier, note}}。"""
    latest = book.latest_actuals(user_id)
    trend = book.trend(user_id)
    out: dict[str, dict] = {}
    for subject in predictor.subjects_in(report):
        raw, full = predictor.predict_subject_raw(report, subject)
        actual = latest.get(subject)
        if actual is None:
            out[subject] = {"actual": None, "raw": raw, "full": full, "execution_gap": 0.0,
                            "declining": False, "multiplier": 1.0, "note": "暂无模考数据"}
            continue
        # 只取"诊断看不到的新信息"：应试丢分（会做却失分）+ 退步趋势。
        # 知识薄弱本身已由规划的 base ROI(权重×(1-掌握))体现，不在此重复加权。
        under_perf = max(0.0, raw - actual) / full   # 应试丢分占比
        declining = trend.get(subject, 0.0) < -1.0
        mult = round(min(1.8, max(0.8, 1 + 1.3 * under_perf + (0.25 if declining else 0.0))), 2)
        note = []
        if under_perf > 0.05:
            note.append(f"模考「会做却失分」约 {round(raw - actual)} 分，加强限时/审题/规范训练")
        if declining:
            note.append("近期模考下滑，优先稳住")
        out[subject] = {"actual": actual, "raw": raw, "full": full,
                        "execution_gap": round(raw - actual, 1), "declining": declining,
                        "multiplier": mult, "note": "；".join(note) or "状态平稳，与诊断一致"}
    return out


def subject_weights(book, report, predictor, user_id: str) -> dict[str, float]:
    return {s: a["multiplier"] for s, a in analyze(book, report, predictor, user_id).items()}
