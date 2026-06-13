"""① 多模态教育文档解析（PRD 1.1）。

统一输出 ParsedProblem（JSON）：题型、题干、选项、LaTeX 公式块、知识点挂载、难度、
以及**手写解题过程的逐步分析**（区分草稿/正式解答、标记错误步骤与错误类型）。

MVP 用 MockEduParser（规则解析，零依赖、可跑）；生产替换：
  - 公式识别：百度 PP-FormulaNet_plus-L（LaTeX 准确率≥99%）
  - 版面分析：阿里云 RecognizeEduPaperStructed（题号/题干/选项/解答区切割）
接口 `EduParser.parse(...)` 不变。
"""
from __future__ import annotations

import re
from typing import Optional, Protocol

from app.schemas import ErrorType, HandwritingStep, ParsedProblem, ProblemType

# 关键词 → 知识点（生产由图谱语义匹配/模型完成；此处规则演示）
_KEYWORD_CONCEPTS: list[tuple[tuple[str, ...], str]] = [
    (("导数", "f′", "f'", "单调", "极值", "最值"), "MATH_DERIV_EXTREME"),
    (("sin", "cos", "三角", "周期", "正弦", "余弦定理"), "MATH_TRIG_FUNC"),
    (("等差",), "MATH_SEQ_ARITH"),
    (("等比", "错位相减"), "MATH_SEQ_GEO"),
    (("数列", "通项", "前n项和", "前 n 项和"), "MATH_SEQ_DEF"),
    (("向量", "垂直", "数量积"), "MATH_VEC"),
    (("概率", "古典概型", "分布列"), "MATH_PROB"),
    (("椭圆", "离心率", "双曲线", "抛物线", "圆锥曲线"), "MATH_CONIC"),
    (("直线", "圆", "相切", "相交"), "MATH_LINE_CIRCLE"),
    (("复数", "虚数", "共轭"), "MATH_COMPLEX"),
    (("不等式", "基本不等式"), "MATH_INEQ"),
    (("函数", "奇函数", "偶函数"), "MATH_FUNC_PROP"),
    # 物理
    (("加速度", "初速度", "匀变速", "匀加速"), "PHY_KINEMATICS"),
    (("牛顿", "合力", "F=ma"), "PHY_NEWTON"),
    (("平抛", "水平抛"), "PHY_PROJECTILE"),
    (("电动势", "内阻", "路端电压", "欧姆定律"), "PHY_CIRCUIT"),
    (("动能", "机械能", "做功"), "PHY_ENERGY"),
    (("单摆", "简谐", "振动"), "PHY_SHM"),
    # 化学
    (("物质的量", "摩尔质量", "摩尔"), "CHEM_MOLE"),
    (("浓度", "mol/L"), "CHEM_CONC"),
    (("平衡移动", "化学平衡", "勒夏特列"), "CHEM_EQUILIBRIUM"),
    (("氧化还原", "还原剂", "氧化剂", "化合价"), "CHEM_REDOX"),
    (("周期律", "原子半径", "同周期"), "CHEM_PERIODIC"),
    # 生物
    (("基因型", "杂交", "显性", "隐性", "孟德尔"), "BIO_GENETICS"),
    (("光合作用", "暗反应", "叶绿体"), "BIO_PHOTOSYNTHESIS"),
    (("呼吸作用", "有氧呼吸", "线粒体"), "BIO_RESPIRATION"),
    (("种群", "生态系统", "J形", "S形"), "BIO_ECOLOGY"),
    (("减数分裂", "有丝分裂", "联会"), "BIO_MITOSIS"),
]

_LATEX_SUP = {"²": "^{2}", "³": "^{3}", "⁴": "^{4}", "ⁿ": "^{n}", "⁺": "^{+}", "ⁱ": "^{i}"}


def to_latex(expr: str) -> str:
    """演示性公式→LaTeX 规整（生产由 PP-FormulaNet 完成）。"""
    out = expr
    for u, l in _LATEX_SUP.items():
        out = out.replace(u, l)
    out = out.replace("√", r"\sqrt").replace("π", r"\pi").replace("≥", r"\ge ")
    out = out.replace("≤", r"\le ").replace("∈", r"\in ").replace("·", r"\cdot ")
    return out


def attach_concepts(text: str) -> list[str]:
    found: list[str] = []
    for kws, cid in _KEYWORD_CONCEPTS:
        if any(k in text for k in kws) and cid not in found:
            found.append(cid)
    return found


class EduParser(Protocol):
    backend: str

    def parse(self, text: str, handwriting: Optional[list[dict]] = None,
              subject: str = "math") -> ParsedProblem: ...


class MockEduParser:
    """规则版解析器：解析 OCR 文本 + 手写步骤分析。"""

    backend = "mock"
    _id_counter = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._id_counter += 1
        return f"{cls._id_counter:04d}"

    def parse(self, text: str, handwriting: Optional[list[dict]] = None,
              subject: str = "math") -> ParsedProblem:
        text = (text or "").strip()
        pid = f"UP{MockEduParser._next_id()}"

        # 选项抽取：行内/换行的 A. B. C. D.
        options: dict[str, str] = {}
        for m in re.finditer(r"([ABCD])[\.．、]\s*([^ABCD\n]+)", text):
            options[m.group(1)] = m.group(2).strip()
        ptype = ProblemType.CHOICE if len(options) >= 2 else (
            ProblemType.BLANK if "____" in text or "填空" in text else ProblemType.SOLUTION)

        # 题干：去掉选项部分
        stem = text
        if options:
            stem = re.split(r"[ABCD][\.．、]", text)[0].strip()

        # 公式块：抽取含数学符号的片段并转 LaTeX
        latex_blocks: list[str] = []
        for frag in re.findall(r"[^，。；,\.\s]*[=²³√π≥≤∈][^，。；,\.\s]*", text):
            lx = to_latex(frag)
            if lx and lx not in latex_blocks:
                latex_blocks.append(lx)

        concepts = attach_concepts(text)
        warnings: list[str] = []
        if not concepts:
            warnings.append("未能从题干自动挂载知识点，建议人工标注或接入语义匹配。")

        parsed = ParsedProblem(
            problem_id=pid, type=ptype, stem=stem, options=options,
            latex_blocks=latex_blocks[:6], concept_ids=concepts,
            difficulty=0.5, parse_confidence=0.9 if concepts else 0.6, warnings=warnings,
            handwriting_steps=self._analyze_handwriting(handwriting or []))
        return parsed

    def _analyze_handwriting(self, steps: list[dict]) -> list[HandwritingStep]:
        """手写解题过程分析：区分草稿/正式解答，标记错误步骤。

        输入每步可含 {text, region('draft'|'answer'), is_error, error_type, note}；
        生产由手写识别 + 步骤级判错模型自动产出，这里透传/规整为结构化结果。
        """
        out: list[HandwritingStep] = []
        for i, s in enumerate(steps):
            et = s.get("error_type")
            out.append(HandwritingStep(
                index=i, text=str(s.get("text", "")),
                region=s.get("region", "answer"),
                is_error=bool(s.get("is_error", False)),
                error_type=ErrorType(et) if et in {e.value for e in ErrorType} else None,
                note=s.get("note", "")))
        return out


class HttpEduParser:
    """生产级 OCR/版面解析客户端：统一 HTTP 网关契约（健壮：超时/重试/降级）。

    网关后端可对接 百度 PP-FormulaNet_plus-L（公式→LaTeX）、阿里云 RecognizeEduPaperStructed
    （版面/题号/选项/解答区切割）、手写识别等，对外暴露统一契约：
      请求  POST {ocr_endpoint}  {"image_base64"|"text", "subject"}
      响应  {"stem","type","options","latex_blocks","concept_hints","handwriting_steps","confidence"}
    可注入 http_client（用 MockTransport 在真实 HTTP 协议层做契约测试）。
    """

    backend = "real"

    def __init__(self, http_client=None) -> None:
        import httpx
        from app.core.config import settings
        self._httpx = httpx
        self.settings = settings
        self.client = http_client or httpx.Client(timeout=settings.ocr_timeout_s)
        self._mock = MockEduParser()

    def parse(self, text: str = "", handwriting=None, subject: str = "math",
              image_base64: Optional[str] = None) -> ParsedProblem:
        payload = {"subject": subject}
        if image_base64:
            payload["image_base64"] = image_base64
        else:
            payload["text"] = text or ""
        last_err = None
        for attempt in range(self.settings.ocr_max_retries + 1):
            try:
                r = self.client.post(self.settings.ocr_endpoint, json=payload,
                                     timeout=self.settings.ocr_timeout_s)
                r.raise_for_status()
                return self._to_parsed(r.json(), handwriting)
            except Exception as e:  # noqa: BLE001
                last_err = e
        # 降级：保证可用性（生产应同时告警）
        fallback = self._mock.parse(text, handwriting, subject)
        fallback.warnings.append(f"OCR 网关不可用，已降级到本地解析：{last_err!r}")
        fallback.parse_confidence = min(fallback.parse_confidence, 0.5)
        return fallback

    def _to_parsed(self, data: dict, handwriting) -> ParsedProblem:
        hw = handwriting if handwriting is not None else data.get("handwriting_steps", [])
        ptype = data.get("type", "solution")
        return ParsedProblem(
            problem_id=f"OCR{MockEduParser._next_id()}",
            type=ProblemType(ptype) if ptype in {t.value for t in ProblemType}
            else ProblemType.SOLUTION,
            stem=data.get("stem", ""), options=data.get("options", {}) or {},
            latex_blocks=data.get("latex_blocks", []) or [],
            concept_ids=data.get("concept_ids") or attach_concepts(data.get("stem", "")),
            difficulty=float(data.get("difficulty", 0.5)),
            parse_confidence=float(data.get("confidence", 0.9)),
            warnings=data.get("warnings", []) or [],
            handwriting_steps=self._mock._analyze_handwriting(hw or []))


class BaiduFormulaParser(HttpEduParser):  # pragma: no cover - 生产路径
    """百度 PP-FormulaNet_plus-L 适配（经统一网关）。生产在网关侧用 access_token 调百度 OCR。"""

    backend = "real-baidu"


def get_parser() -> EduParser:
    from app.core.config import settings
    if settings.ocr_endpoint:
        try:
            return HttpEduParser()
        except Exception:
            pass
    return MockEduParser()


PARSER: EduParser = get_parser()
