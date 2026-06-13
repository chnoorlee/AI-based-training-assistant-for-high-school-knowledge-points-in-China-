"""变式题人工审核存储与流程（PRD 4.2：生成题须经≥1 名一线教师审核方可入库）。

状态机：AUTO_REJECTED（机审未过，不入队） / PENDING（待人审） → APPROVED / REJECTED。
仅 APPROVED 可入库被使用。内存实现，生产替换为 DB，接口不变。
"""
from __future__ import annotations

import threading

from app.schemas import GeneratedVariant, VariantReviewStatus


class VariantStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.variants: dict[str, GeneratedVariant] = {}
        self._counter = 0

    def next_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"VAR{self._counter:05d}"

    def add(self, v: GeneratedVariant) -> None:
        with self._lock:
            self.variants[v.id] = v

    def get(self, vid: str) -> GeneratedVariant | None:
        return self.variants.get(vid)

    def pending(self) -> list[GeneratedVariant]:
        return [v for v in self.variants.values()
                if v.review_status == VariantReviewStatus.PENDING]

    def approved(self) -> list[GeneratedVariant]:
        return [v for v in self.variants.values()
                if v.review_status == VariantReviewStatus.APPROVED]

    def review(self, vid: str, approve: bool, reviewer: str,
               note: str = "") -> GeneratedVariant | None:
        with self._lock:
            v = self.variants.get(vid)
            if v is None or v.review_status != VariantReviewStatus.PENDING:
                return v
            v.review_status = (VariantReviewStatus.APPROVED if approve
                               else VariantReviewStatus.REJECTED)
            v.reviewer = reviewer
            v.review_note = note
            return v

    def reset(self) -> None:
        with self._lock:
            self.variants.clear()
            self._counter = 0


VARIANT_STORE = VariantStore()
