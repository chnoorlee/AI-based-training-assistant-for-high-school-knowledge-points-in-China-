"""变式题生成编排（PRD 4.2）。

流程：选模板（按种子题/考点）→ 采样参数 + 情境 → 符号求解构造题目 → 质量流水线
→ 通过则入审核队列(PENDING)，否则标 AUTO_REJECTED。批内去重，保证多样性。
"""
from __future__ import annotations

import random
from typing import Optional

from app.data.problem_bank import BANK
from app.schemas import (
    GeneratedVariant,
    Problem,
    Subject,
    VariantGenerateRequest,
    VariantReviewStatus,
)
from app.modules.variant.quality import run_quality
from app.modules.variant.review import VARIANT_STORE
from app.modules.variant.templates import (
    CONCEPT_TO_TEMPLATES, TEMPLATES, pick_scenario,
)


class VariantGenerator:
    def select_template_ids(self, problem_id: Optional[str],
                            concept_id: Optional[str]) -> list[str]:
        ids: list[str] = []
        if problem_id and BANK.get(problem_id):
            for c in BANK.get(problem_id).concept_ids:
                ids += CONCEPT_TO_TEMPLATES.get(c, [])
        elif concept_id:
            ids += CONCEPT_TO_TEMPLATES.get(concept_id, [])
        ids = list(dict.fromkeys(ids))  # 去重保序
        return ids or list(TEMPLATES.keys())

    def generate(self, req: VariantGenerateRequest, seed: Optional[int] = None,
                 max_rejected: int = 3) -> list[GeneratedVariant]:
        rng = random.Random(seed)
        tpl_ids = self.select_template_ids(req.problem_id, req.concept_id)
        results: list[GeneratedVariant] = []
        batch_stems: list[str] = []
        seen_sigs: set[tuple] = set()  # (模板, 参数签名) 去重，避免重复采样
        rejected_shown = 0
        attempts, max_attempts = 0, max(req.count * 8, 16)
        passed = 0

        while passed < req.count and attempts < max_attempts:
            attempts += 1
            tpl = TEMPLATES[tpl_ids[attempts % len(tpl_ids)]]
            params = tpl.sample_params(rng)
            sig = (tpl.id, tuple(sorted(params.items())))
            if sig in seen_sigs:  # 同模板同参数 → 跳过，重采
                continue
            seen_sigs.add(sig)
            scenario = pick_scenario(tpl.scenario_kind, rng, req.scenario_category)
            fields = tpl.build(params, scenario, rng)

            report = run_quality(fields, tpl.base_difficulty, tpl.base_discrimination,
                                 batch_stems)
            vid = VARIANT_STORE.next_id()
            problem = Problem(
                id=vid, subject=Subject.MATH, type=fields["type"],
                concept_ids=fields["concept_ids"],
                difficulty=report.predicted_difficulty,
                discrimination=report.predicted_discrimination,
                ability=fields["ability"], stem=fields["stem"],
                options=fields.get("options", {}), answer=fields["answer"],
                solution_steps=fields["solution_steps"],
                socratic_questions=fields["socratic_questions"],
                common_errors=fields.get("common_errors", []),
                source=f"AI变式（模板 {tpl.id}，待审核）")
            status = (VariantReviewStatus.PENDING if report.auto_passed
                      else VariantReviewStatus.AUTO_REJECTED)
            variant = GeneratedVariant(
                id=vid, template_id=tpl.id, source_problem_id=req.problem_id,
                scenario_category=(scenario.category if scenario else None),
                problem=problem, quality=report, review_status=status)

            if report.auto_passed:
                batch_stems.append(fields["stem"])
                VARIANT_STORE.add(variant)  # 入审核队列
                results.append(variant)
                passed += 1
            elif rejected_shown < max_rejected:
                rejected_shown += 1
                results.append(variant)  # 返回少量被拒样本以透明化
        return results


GENERATOR = VariantGenerator()
