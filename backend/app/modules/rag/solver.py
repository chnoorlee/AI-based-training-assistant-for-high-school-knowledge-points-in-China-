"""解题编排（PRD 2.1 / 2.2 + 绝对禁止事项 #2）。

硬约束落地：
  - 禁止"上传即给答案"：首次解析最多到 HINT（仅 3 个苏格拉底引导问题）；
    需逐级 HINT → GUIDED → FULL，且不可跳级（由 STORE 的解题进度门控）。
  - 完整思维链：FULL 级别展示标准解法全过程，而非只甩结论。
  - 幻觉抑制：输出知识点逐一对照知识图谱核验，未命中者标记「待人工复核」。
  - 数学正确性：命中题库的题用标准解法（绝不让 Mock 现算）；自由输入接入真实教育大模型时
    在 FULL 级给出完整解答（经内容安全 + 知识点核验护栏），Mock 模式仍只给方法论引导、不杜撰答案。
"""
from __future__ import annotations

from app.core.config import settings
from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.modules.rag.llm import LLM
from app.modules.rag.reranker import RERANKER
from app.modules.rag.retriever import RETRIEVER
from app.schemas import FactCheck, Problem, RevealLevel, SolveRequest, SolveResponse
from app.services.store import STORE

MATCH_THRESHOLD = 0.45  # 检索分高于此值视为命中题库（含变式）

_NOTICE = {
    0: "已为你定位考点并给出引导问题。请先动笔尝试，准备好后再获取分步思路——"
       "按平台规定，我们不会直接给答案，而是陪你一步步想清楚。",
    1: "这是分步解题思路（暂不含最终答案）。试着沿着步骤推进，仍有困难再查看完整解析。",
    2: "以下是完整思维链与答案，请对照你自己的过程，定位是哪一步卡住了。",
}


class Solver:
    def solve(self, req: SolveRequest) -> SolveResponse:
        # ① 解析输入 → 检索 → 重排
        query = req.stem or (BANK.get(req.problem_id).stem
                             if req.problem_id and BANK.get(req.problem_id) else "")
        recalled = RETRIEVER.retrieve(query, top_k=10)
        reranked = RERANKER.rerank(query, recalled, top_k=settings.rerank_top_k)
        context_ids = [c.id for c, _ in reranked]

        # ② 命中题库判定
        problem = BANK.get(req.problem_id) if req.problem_id else None
        if problem is None:
            for c, sc in reranked:
                if c.kind == "problem" and sc >= MATCH_THRESHOLD:
                    problem = BANK.get(c.ref_id)
                    break
        pid = problem.id if problem else (req.problem_id or "FREEFORM")

        # ③ 概念与知识点
        if problem:
            concept_ids = list(problem.concept_ids)
        else:
            concept_ids = [c.ref_id for c, _ in reranked if c.kind == "concept"][:2]
        concept_names = [KG.name_of(c) for c in concept_ids]

        # ④ 揭示级别门控（不可跳级；首次最多 HINT）
        served = STORE.get_solve_level(req.user_id, pid)
        effective = max(0, min(int(req.reveal_level), served + 1))
        STORE.set_solve_level(req.user_id, pid, effective)

        resp = SolveResponse(
            problem_id=pid, reveal_level=RevealLevel(effective),
            knowledge_points=concept_names, retrieved_context_ids=context_ids)

        ctx = [c.text for c, _ in reranked[:3]]
        guard_note = ""

        # ⑤ 苏格拉底引导（任何级别都先给）
        if problem and problem.socratic_questions:
            resp.socratic_questions = list(problem.socratic_questions)
        else:
            resp.socratic_questions = LLM.socratic_questions(query, concept_names, ctx)

        # ⑥ 分步 / 完整解析
        if effective >= int(RevealLevel.GUIDED):
            if problem:
                steps = problem.solution_steps
                resp.guided_steps = steps[:-1] if len(steps) > 1 else steps  # 暂扣最终一步
            else:
                resp.guided_steps = LLM.guided_steps(query, concept_names, ctx)

        if effective >= int(RevealLevel.FULL):
            if problem:
                resp.chain_of_thought = list(problem.solution_steps)
                resp.guided_steps = list(problem.solution_steps)
                resp.final_answer = problem.answer
            else:
                guard_note = self._full_free_input(resp, query, concept_names, ctx)

        # ⑦ 幻觉抑制：知识点核验（命中题库用 concept_ids；自由输入在 ⑥ 已就地核验）
        if problem or not resp.knowledge_points or effective < int(RevealLevel.FULL):
            verified = [KG.name_of(c) for c in concept_ids if KG.get(c)]
            unverified = [c for c in concept_ids if not KG.get(c)]
            resp.fact_check = FactCheck(verified_concepts=verified,
                                        unverified_claims=unverified, passed=not unverified)

        # ⑧ 提示语
        notice = _NOTICE[effective]
        if effective < int(req.reveal_level):
            notice = "为保证学习效果，解析按 引导→分步→完整 逐级展开。" + notice
        if effective >= int(RevealLevel.FULL) and not problem:
            notice += guard_note
        resp.notice = notice
        return resp

    def _full_free_input(self, resp: SolveResponse, query: str,
                         concept_names: list[str], ctx: list[str]) -> str:
        """自由输入题在 FULL 级的完整解答 + 安全/幻觉护栏。返回提示补充语。"""
        from app.modules.rag.guards import content_safe, verify_knowledge_points
        sol = LLM.full_solution(query, concept_names, ctx)
        resp.guided_steps = list(sol.get("steps", []))
        resp.chain_of_thought = list(sol.get("steps", []))
        kps = sol.get("knowledge_points") or concept_names
        verified, unverified = verify_knowledge_points(kps)
        resp.knowledge_points = (verified + unverified) or concept_names
        safe, issues = content_safe(" ".join(resp.chain_of_thought) + " "
                                    + str(sol.get("answer") or ""))
        resp.fact_check = FactCheck(verified_concepts=verified, unverified_claims=unverified,
                                    passed=safe and not unverified)
        # 仅当 真实模型 + 内容安全 + 知识点不全是未核验 时，才放行最终答案
        if LLM.is_real and sol.get("answer") and safe and len(verified) >= len(unverified):
            resp.final_answer = sol["answer"]
            return "（以上由教育大模型生成并经知识点核验，仅供参考，请结合教材自查。）"
        resp.final_answer = None
        if not safe:
            return f"（检测到内容风险 {issues}，已拦截最终答案，转人工复核。）"
        return "（此为自由输入题，已提供方法论引导；接入教育大模型后将给出完整解答与答案。）"

    def solve_problem(self, user_id: str, problem: Problem,
                      reveal_level: RevealLevel) -> SolveResponse:
        """对给定题目（如审核通过的变式题）走同一套苏格拉底门控解题。"""
        pid = problem.id
        concept_ids = list(problem.concept_ids)
        concept_names = [KG.name_of(c) for c in concept_ids]

        served = STORE.get_solve_level(user_id, pid)
        effective = max(0, min(int(reveal_level), served + 1))
        STORE.set_solve_level(user_id, pid, effective)

        resp = SolveResponse(problem_id=pid, reveal_level=RevealLevel(effective),
                             knowledge_points=concept_names)
        resp.socratic_questions = (list(problem.socratic_questions)
                                   if problem.socratic_questions
                                   else LLM.socratic_questions(problem.stem, concept_names, []))
        if effective >= int(RevealLevel.GUIDED):
            steps = problem.solution_steps
            resp.guided_steps = steps[:-1] if len(steps) > 1 else list(steps)
        if effective >= int(RevealLevel.FULL):
            resp.chain_of_thought = list(problem.solution_steps)
            resp.guided_steps = list(problem.solution_steps)
            resp.final_answer = problem.answer

        verified = [KG.name_of(c) for c in concept_ids if KG.get(c)]
        unverified = [c for c in concept_ids if not KG.get(c)]
        resp.fact_check = FactCheck(verified_concepts=verified,
                                    unverified_claims=unverified, passed=not unverified)
        notice = _NOTICE[effective]
        if effective < int(reveal_level):
            notice = "为保证学习效果，解析按 引导→分步→完整 逐级展开。" + notice
        resp.notice = notice
        return resp


SOLVER = Solver()
