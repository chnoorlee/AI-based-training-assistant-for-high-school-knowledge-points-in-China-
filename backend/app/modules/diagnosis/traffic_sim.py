"""把合成流量写入存储，模拟「真实作答日志」——仅用于演示 / 压测 / 集成测试。

生产中真实用户通过 /answer 写入；此处用合成过程批量回填，让训练流水线有日志可接入。
与训练解耦：流水线只从 LogRepository 读，不关心数据是真实还是模拟。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from app.data.problem_bank import BANK
from app.modules.diagnosis.synthetic import generate_synthetic_logs
from app.schemas import ResponseRecord


def simulate_traffic_to_store(n_students: int, ts_start: datetime, ts_end: datetime,
                              seed: int = 0, user_prefix: str = "sim", store=None) -> int:
    """生成 n_students 名学生的作答序列并写入 STORE，时间戳均匀落在 [ts_start, ts_end]。"""
    from app.services.store import STORE
    store = store or STORE

    diff = BANK.difficulty_vector()
    disc = np.array([BANK.problems[p].discrimination for p in BANK.problem_ids])
    data = generate_synthetic_logs(BANK.q_matrix, diff, disc, n_students=n_students, seed=seed)

    span = max((ts_end - ts_start).total_seconds(), 1.0)
    rng = np.random.default_rng(seed)
    written = 0
    # 用合成的完整序列（train 前缀 + 最后一题）还原每个学生的作答流
    for sid, prefix_items, prefix_corrects, last_item, last_correct, *_ in data.test_points:
        items = list(prefix_items) + [last_item]
        corrects = list(prefix_corrects) + [last_correct]
        uid = f"{user_prefix}_{seed}_{sid}"
        # 该生的时间戳：在窗口内随机起点后单调递增
        t0 = ts_start + timedelta(seconds=float(rng.uniform(0, span * 0.5)))
        step = timedelta(seconds=span / max(len(items), 1) * 0.5)
        for k, (it, c) in enumerate(zip(items, corrects)):
            pid = BANK.problem_ids[it]
            p = BANK.get(pid)
            ts = min(t0 + step * k, ts_end)
            store.add_response(ResponseRecord(
                user_id=uid, problem_id=pid, correct=bool(c),
                time_spent_s=float(rng.uniform(20, 180)), ts=ts,
                concept_ids=list(p.concept_ids), difficulty=p.difficulty))
            written += 1
    return written


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
