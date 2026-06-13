"""数学学科种子数据：知识点（图谱节点）+ 高考风格题目。

说明：
- 题干使用 Unicode 数学符号（²³√π≥≤∈⊥∞°），规避 LaTeX 反斜杠转义，渲染清晰；
  生产环境由解析模块输出标准 LaTeX，本骨架的 parsing 模块演示了 LaTeX 块输出。
- 所有题目均为「高考风格自编/改编题」，附知识点、难度、区分度、苏格拉底引导问、
  解题步骤（思维链）、易错点。绝非真题照搬，符合知识产权要求。
- difficulty 0~1（越大越难），discrimination 0~1（区分度）。
"""
from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# 知识点（按模块组织，含先修边与跨学科关联）
# 字段：id, name, module, ability, prereq_ids, cross_subject_ids
# ──────────────────────────────────────────────────────────────
CONCEPTS: list[dict] = [
    {"id": "MATH_SET", "name": "集合与常用逻辑用语", "module": "预备知识",
     "ability": "memory", "prereq_ids": [], "cross_subject_ids": []},
    {"id": "MATH_FUNC_BASIC", "name": "函数的概念与表示", "module": "函数与导数",
     "ability": "understand", "prereq_ids": ["MATH_SET"], "cross_subject_ids": []},
    {"id": "MATH_FUNC_PROP", "name": "函数的单调性与奇偶性", "module": "函数与导数",
     "ability": "understand", "prereq_ids": ["MATH_FUNC_BASIC"], "cross_subject_ids": []},
    {"id": "MATH_EXP_LOG", "name": "指数函数与对数函数", "module": "函数与导数",
     "ability": "apply", "prereq_ids": ["MATH_FUNC_BASIC"], "cross_subject_ids": []},
    {"id": "MATH_DERIV_DEF", "name": "导数的概念与运算", "module": "函数与导数",
     "ability": "apply", "prereq_ids": ["MATH_FUNC_PROP"], "cross_subject_ids": ["PHY_VELOCITY(瞬时速度)"]},
    {"id": "MATH_DERIV_MONO", "name": "导数与函数单调性", "module": "函数与导数",
     "ability": "analyze", "prereq_ids": ["MATH_DERIV_DEF", "MATH_FUNC_PROP"], "cross_subject_ids": []},
    {"id": "MATH_DERIV_EXTREME", "name": "导数与极值最值", "module": "函数与导数",
     "ability": "analyze", "prereq_ids": ["MATH_DERIV_MONO"], "cross_subject_ids": []},
    {"id": "MATH_TRIG_FUNC", "name": "三角函数的图象与性质", "module": "三角函数",
     "ability": "understand", "prereq_ids": ["MATH_FUNC_BASIC"], "cross_subject_ids": ["PHY_SHM(简谐运动)"]},
    {"id": "MATH_TRIG_IDENT", "name": "三角恒等变换", "module": "三角函数",
     "ability": "apply", "prereq_ids": ["MATH_TRIG_FUNC"], "cross_subject_ids": []},
    {"id": "MATH_SOLVE_TRIANGLE", "name": "解三角形（正弦/余弦定理）", "module": "三角函数",
     "ability": "apply", "prereq_ids": ["MATH_TRIG_IDENT"], "cross_subject_ids": ["PHY_FORCE(力的合成)"]},
    {"id": "MATH_VEC", "name": "平面向量", "module": "平面向量",
     "ability": "apply", "prereq_ids": [], "cross_subject_ids": ["PHY_VECTOR(矢量运算)"]},
    {"id": "MATH_SEQ_DEF", "name": "数列的概念与通项", "module": "数列",
     "ability": "understand", "prereq_ids": [], "cross_subject_ids": []},
    {"id": "MATH_SEQ_ARITH", "name": "等差数列", "module": "数列",
     "ability": "apply", "prereq_ids": ["MATH_SEQ_DEF"], "cross_subject_ids": []},
    {"id": "MATH_SEQ_GEO", "name": "等比数列", "module": "数列",
     "ability": "apply", "prereq_ids": ["MATH_SEQ_DEF"], "cross_subject_ids": []},
    {"id": "MATH_SEQ_SUM", "name": "数列求和（错位相减/裂项）", "module": "数列",
     "ability": "analyze", "prereq_ids": ["MATH_SEQ_ARITH", "MATH_SEQ_GEO"], "cross_subject_ids": []},
    {"id": "MATH_SOLID_GEO", "name": "立体几何（线面位置关系）", "module": "立体几何",
     "ability": "understand", "prereq_ids": [], "cross_subject_ids": []},
    {"id": "MATH_SOLID_VEC", "name": "空间向量与立体几何", "module": "立体几何",
     "ability": "analyze", "prereq_ids": ["MATH_VEC", "MATH_SOLID_GEO"], "cross_subject_ids": []},
    {"id": "MATH_LINE_CIRCLE", "name": "直线与圆", "module": "解析几何",
     "ability": "apply", "prereq_ids": [], "cross_subject_ids": []},
    {"id": "MATH_CONIC", "name": "圆锥曲线（椭圆/双曲线/抛物线）", "module": "解析几何",
     "ability": "analyze", "prereq_ids": ["MATH_LINE_CIRCLE"], "cross_subject_ids": []},
    {"id": "MATH_PROB", "name": "概率（古典/条件/分布列）", "module": "概率统计",
     "ability": "apply", "prereq_ids": [], "cross_subject_ids": ["BIO_GENETICS(遗传概率)"]},
    {"id": "MATH_STAT", "name": "统计（抽样/回归/正态分布）", "module": "概率统计",
     "ability": "apply", "prereq_ids": ["MATH_PROB"], "cross_subject_ids": []},
    {"id": "MATH_INEQ", "name": "不等式（基本不等式/解不等式）", "module": "不等式",
     "ability": "apply", "prereq_ids": [], "cross_subject_ids": []},
    {"id": "MATH_COMPLEX", "name": "复数", "module": "复数",
     "ability": "understand", "prereq_ids": [], "cross_subject_ids": []},
]


# ──────────────────────────────────────────────────────────────
# 题目
# ──────────────────────────────────────────────────────────────
PROBLEMS: list[dict] = [
    {
        "id": "M0001", "type": "choice", "concept_ids": ["MATH_FUNC_PROP"],
        "difficulty": 0.25, "discrimination": 0.45, "ability": "understand",
        "stem": "设函数 f(x)=x³+x，则 f(x) 是（　）",
        "options": {
            "A": "奇函数，且在 R 上单调递增", "B": "偶函数，且在 R 上单调递增",
            "C": "奇函数，且在 R 上单调递减", "D": "偶函数，且在 R 上单调递减"},
        "answer": "A",
        "solution_steps": [
            "判断奇偶性：f(-x)=(-x)³+(-x)=-x³-x=-(x³+x)=-f(x)，故 f(x) 为奇函数。",
            "判断单调性：f′(x)=3x²+1>0 在 R 上恒成立，故 f(x) 在 R 上单调递增。",
            "综上选 A。"],
        "socratic_questions": [
            "判断奇偶性，应该比较 f(-x) 与 f(x)、-f(x) 的关系，你能先算出 f(-x) 吗？",
            "要说明单调性，对 f(x) 求导后，f′(x) 的符号能告诉你什么？",
            "x³ 和 x 在 R 上各自的单调性如何？叠加之后呢？"],
        "common_errors": ["误把 x³+x 当成偶函数", "未验证定义域关于原点对称就下奇偶性结论"],
        "source": "自编（人教A版必修一改编，已授权）",
    },
    {
        "id": "M0002", "type": "solution", "concept_ids": ["MATH_DERIV_MONO", "MATH_DERIV_EXTREME"],
        "difficulty": 0.45, "discrimination": 0.6, "ability": "analyze",
        "stem": "已知函数 f(x)=x³-3x，求 f(x) 的单调区间与极值。",
        "options": {},
        "answer": "增区间 (-∞,-1) 和 (1,+∞)，减区间 (-1,1)；极大值 f(-1)=2，极小值 f(1)=-2。",
        "solution_steps": [
            "求导：f′(x)=3x²-3=3(x-1)(x+1)。",
            "令 f′(x)=0，得 x=-1 或 x=1，将定义域分为三段。",
            "判号：x<-1 时 f′>0（增）；-1<x<1 时 f′<0（减）；x>1 时 f′>0（增）。",
            "故增区间 (-∞,-1) 与 (1,+∞)，减区间 (-1,1)。",
            "极大值 f(-1)=(-1)³-3(-1)=2，极小值 f(1)=1-3=-2。"],
        "socratic_questions": [
            "求单调区间，第一步通常要对函数做什么运算？",
            "解出 f′(x)=0 的根后，它们把定义域分成了几段？每段如何取符号？",
            "极大值还是极小值，你打算怎么由 f′ 的符号变化来判断？"],
        "common_errors": ["把极值点 x 当作极值写出", "区间开闭/并写成 ∪ 错误", "导数符号判断颠倒"],
        "source": "自编",
    },
    {
        "id": "M0003", "type": "solution", "concept_ids": ["MATH_DERIV_EXTREME", "MATH_EXP_LOG"],
        "difficulty": 0.8, "discrimination": 0.7, "ability": "analyze",
        "stem": "已知函数 f(x)=eˣ-ax。若 f(x)≥0 对一切 x∈R 恒成立，求实数 a 的取值范围。",
        "options": {},
        "answer": "0 ≤ a ≤ e。",
        "solution_steps": [
            "「对一切 x 成立」转化为 f(x) 的最小值 ≥ 0。",
            "当 a≤0：若 a=0，f(x)=eˣ>0 成立；若 a<0，x→-∞ 时 -ax→-∞，f→-∞，不成立。",
            "当 a>0：f′(x)=eˣ-a=0 得 x=ln a，此为最小值点。",
            "最小值 f(ln a)=e^{ln a}-a·ln a=a-a·ln a=a(1-ln a)。",
            "令 a(1-ln a)≥0，因 a>0，需 1-ln a≥0，即 ln a≤1，a≤e。",
            "综合三种情形：0 ≤ a ≤ e。"],
        "socratic_questions": [
            "「f(x)≥0 对一切 x 成立」最常见的转化是求谁的最值？把它写成不等式试试。",
            "这里含参数 a，是否需要对 a 的符号分类讨论？先看 a≤0 会发生什么？",
            "当 a>0 时用导数求出最小值点后，最小值表达式 ≥0 化简能得到关于 a 的什么不等式？"],
        "common_errors": ["漏掉 a≤0 的讨论", "最小值点 x=ln a 代入算错", "端点 a=e 取舍错误"],
        "source": "自编（导数恒成立问题）",
    },
    {
        "id": "M0004", "type": "choice", "concept_ids": ["MATH_TRIG_FUNC"],
        "difficulty": 0.3, "discrimination": 0.4, "ability": "understand",
        "stem": "函数 y=2sin(2x+π/6) 的最小正周期为（　）",
        "options": {"A": "π/2", "B": "π", "C": "2π", "D": "4π"},
        "answer": "B",
        "solution_steps": ["对 y=Asin(ωx+φ)，最小正周期 T=2π/|ω|。", "此处 ω=2，故 T=2π/2=π，选 B。"],
        "socratic_questions": [
            "形如 sin(ωx+φ) 的最小正周期公式是什么？",
            "这道题里 ω 等于多少？",
            "前面的振幅 2 会不会影响周期？为什么？"],
        "common_errors": ["把振幅当作影响周期的量", "用 2π/(2+π/6) 这种错误式子"],
        "source": "自编",
    },
    {
        "id": "M0005", "type": "solution", "concept_ids": ["MATH_SOLVE_TRIANGLE"],
        "difficulty": 0.4, "discrimination": 0.55, "ability": "apply",
        "stem": "在 △ABC 中，已知 a=2，c=3，B=60°，求边 b。",
        "options": {},
        "answer": "b=√7。",
        "solution_steps": [
            "已知两边及其夹角，求第三边，用余弦定理。",
            "b²=a²+c²-2ac·cosB=2²+3²-2·2·3·cos60°=4+9-12×0.5=7。",
            "故 b=√7。"],
        "socratic_questions": [
            "已知两边和它们的夹角，求第三边，应该用正弦定理还是余弦定理？",
            "你能把余弦定理 b²=a²+c²-2ac·cosB 写出来吗？",
            "cos60° 的值是多少？代进去算一算。"],
        "common_errors": ["余弦定理写成 a²+c²+2ac·cosB（符号错）", "cos60° 记成 √3/2"],
        "source": "自编",
    },
    {
        "id": "M0006", "type": "solution", "concept_ids": ["MATH_SEQ_ARITH", "MATH_SEQ_SUM"],
        "difficulty": 0.35, "discrimination": 0.5, "ability": "apply",
        "stem": "等差数列 {aₙ} 中，a₁=1，公差 d=2，求前 n 项和 Sₙ。",
        "options": {},
        "answer": "Sₙ=n²。",
        "solution_steps": [
            "通项 aₙ=a₁+(n-1)d=1+(n-1)·2=2n-1。",
            "前 n 项和 Sₙ=n(a₁+aₙ)/2=n(1+2n-1)/2=n·2n/2=n²。"],
        "socratic_questions": [
            "等差数列的通项公式 aₙ= ? 你能先把 aₙ 求出来吗？",
            "前 n 项和有两个常用公式，分别是什么？这里哪个更方便？",
            "代入 a₁ 和 aₙ 后，能不能化简成一个简洁的式子？"],
        "common_errors": ["通项 2n-1 误写成 2n+1", "求和公式 n(a₁+aₙ)/2 与 na₁+n(n-1)d/2 混用出错"],
        "source": "自编",
    },
    {
        "id": "M0007", "type": "solution", "concept_ids": ["MATH_SEQ_GEO", "MATH_SEQ_SUM"],
        "difficulty": 0.75, "discrimination": 0.7, "ability": "analyze",
        "stem": "已知等比数列 {aₙ} 满足 a₁=2，公比 q=2。设 Tₙ=Σ_{k=1}^{n} k·aₖ，求 Tₙ。",
        "options": {},
        "answer": "Tₙ=(n-1)·2ⁿ⁺¹+2。",
        "solution_steps": [
            "通项 aₙ=2·2ⁿ⁻¹=2ⁿ，故 Tₙ=Σ k·2ᵏ，是「等差×等比」型，用错位相减。",
            "写出 Tₙ=1·2+2·2²+…+n·2ⁿ；两边乘 2 得 2Tₙ=1·2²+2·2³+…+n·2ⁿ⁺¹。",
            "错位相减：Tₙ-2Tₙ=(2+2²+…+2ⁿ)-n·2ⁿ⁺¹。",
            "等比求和 2+2²+…+2ⁿ=2ⁿ⁺¹-2，故 -Tₙ=(2ⁿ⁺¹-2)-n·2ⁿ⁺¹。",
            "整理得 Tₙ=(n-1)·2ⁿ⁺¹+2。（可代 n=1 验证：T₁=0·4+2=2=1·2 ✓）"],
        "socratic_questions": [
            "通项是 k·2ᵏ，属于「等差乘等比」结构，这类求和最经典的方法叫什么？",
            "做错位相减时，Tₙ 要乘以公比几，然后两式如何对齐错位？",
            "两式相减后，中间会出现一个等比数列，你能把它单独求和吗？"],
        "common_errors": ["错位对齐错位数", "相减后漏减最后一项 n·2ⁿ⁺¹", "最终常数项符号算错"],
        "source": "自编（错位相减经典模型）",
    },
    {
        "id": "M0008", "type": "choice", "concept_ids": ["MATH_VEC"],
        "difficulty": 0.3, "discrimination": 0.45, "ability": "apply",
        "stem": "已知向量 a=(1,2)，b=(2,k)。若 a⊥b，则 k=（　）",
        "options": {"A": "1", "B": "-1", "C": "4", "D": "-4"},
        "answer": "B",
        "solution_steps": ["两向量垂直 ⟺ 数量积为 0。", "a·b=1×2+2×k=2+2k=0，解得 k=-1，选 B。"],
        "socratic_questions": [
            "两个向量垂直，对应它们的数量积应该等于多少？",
            "坐标形式下，a·b 怎么计算？",
            "由此你能列出关于 k 的方程并解出来吗？"],
        "common_errors": ["垂直条件与平行条件 x₁y₂-x₂y₁=0 混淆"],
        "source": "自编",
    },
    {
        "id": "M0009", "type": "solution", "concept_ids": ["MATH_LINE_CIRCLE"],
        "difficulty": 0.45, "discrimination": 0.55, "ability": "apply",
        "stem": "判断直线 l：y=x+1 与圆 x²+y²=1 的位置关系。",
        "options": {},
        "answer": "相交。",
        "solution_steps": [
            "圆 x²+y²=1 的圆心为 (0,0)，半径 r=1。",
            "将 l 写成一般式 x-y+1=0，圆心到 l 的距离 d=|0-0+1|/√(1²+(-1)²)=1/√2≈0.707。",
            "因 d=1/√2<1=r，故直线与圆相交。"],
        "socratic_questions": [
            "判断直线与圆的位置关系，通常比较哪两个量？",
            "点到直线的距离公式你还记得吗？先把直线写成一般式。",
            "算出的 d 与半径 r 有三种大小关系，分别对应相离、相切、相交，这里属于哪种？"],
        "common_errors": ["距离公式分母忘记开方", "把直线系数代错导致 d 计算错误"],
        "source": "自编",
    },
    {
        "id": "M0010", "type": "solution", "concept_ids": ["MATH_CONIC"],
        "difficulty": 0.4, "discrimination": 0.5, "ability": "apply",
        "stem": "求椭圆 x²/4 + y² = 1 的离心率。",
        "options": {},
        "answer": "e=√3/2。",
        "solution_steps": [
            "椭圆标准方程中 a²=4，b²=1（a²>b²，焦点在 x 轴）。",
            "c²=a²-b²=4-1=3，c=√3。",
            "离心率 e=c/a=√3/2。"],
        "socratic_questions": [
            "椭圆标准方程里 a² 和 b² 哪个大？焦点在哪条轴上？",
            "a、b、c 之间满足什么关系式？（注意椭圆与双曲线不同）",
            "离心率 e 的定义是什么？"],
        "common_errors": ["用了双曲线的 c²=a²+b²", "a 与 b 取反导致 e>1"],
        "source": "自编",
    },
    {
        "id": "M0011", "type": "solution", "concept_ids": ["MATH_PROB"],
        "difficulty": 0.4, "discrimination": 0.5, "ability": "apply",
        "stem": "一个袋中装有 3 个红球、2 个白球，共 5 个球。从中任取 2 个，求恰好取到 1 红 1 白的概率。",
        "options": {},
        "answer": "3/5。",
        "solution_steps": [
            "古典概型，样本空间总数 C(5,2)=10。",
            "「恰好 1 红 1 白」有利结果数 C(3,1)·C(2,1)=3×2=6。",
            "概率 P=6/10=3/5。"],
        "socratic_questions": [
            "这是不是古典概型？任取 2 个球的所有等可能结果共有多少种？",
            "「恰好 1 红 1 白」该怎样用组合数来计数？红、白分别取几个？",
            "有利结果数除以总数，得到的概率是多少？"],
        "common_errors": ["分母误用排列 A(5,2)", "忘记红白两类的取法要相乘"],
        "source": "自编",
    },
    {
        "id": "M0012", "type": "choice", "concept_ids": ["MATH_INEQ"],
        "difficulty": 0.35, "discrimination": 0.5, "ability": "apply",
        "stem": "已知 x>0，则 x+4/x 的最小值为（　）",
        "options": {"A": "2", "B": "4", "C": "8", "D": "不存在"},
        "answer": "B",
        "solution_steps": [
            "x>0 时，由基本不等式 a+b≥2√(ab)（a,b>0）。",
            "x+4/x≥2√(x·4/x)=2√4=4，当且仅当 x=4/x，即 x=2 时取等。",
            "故最小值为 4，选 B。"],
        "socratic_questions": [
            "基本不等式 a+b≥2√(ab) 成立的前提条件是什么？这里满足吗？",
            "把 x 和 4/x 看作两个数，它们的乘积是不是定值？这一步为什么关键？",
            "取等号的条件是什么？解出来的 x 在定义域内吗？"],
        "common_errors": ["忽略 x>0 的前提", "不验证取等条件就下最小值结论", "乘积非定值仍硬套"],
        "source": "自编",
    },
    {
        "id": "M0013", "type": "solution", "concept_ids": ["MATH_SOLID_VEC", "MATH_SOLID_GEO"],
        "difficulty": 0.6, "discrimination": 0.65, "ability": "analyze",
        "stem": "正方体 ABCD-A₁B₁C₁D₁ 中，求异面直线 AB₁ 与 BC₁ 所成角的大小。",
        "options": {},
        "answer": "60°。",
        "solution_steps": [
            "设棱长为 1，建立空间直角坐标系：A(0,0,0),B(1,0,0),C(1,1,0),A₁(0,0,1),B₁(1,0,1),C₁(1,1,1)。",
            "向量 AB₁=(1,0,1)，BC₁=(0,1,1)。",
            "数量积 AB₁·BC₁=1×0+0×1+1×1=1；|AB₁|=√2，|BC₁|=√2。",
            "cosθ=|AB₁·BC₁|/(|AB₁||BC₁|)=1/(√2·√2)=1/2。",
            "故异面直线所成角 θ=60°。"],
        "socratic_questions": [
            "求异面直线所成角，常用「平移找角」和「空间向量」两种方法，你更想用哪种？",
            "如果建立坐标系，正方体的八个顶点坐标你能写出来吗？",
            "用向量求出的夹角余弦为什么要加绝对值？异面直线所成角的范围是多少？"],
        "common_errors": ["不加绝对值得到钝角", "坐标系建立或顶点坐标写错", "把所成角范围当成 (0°,180°)"],
        "source": "自编（空间向量法）",
    },
    {
        "id": "M0014", "type": "choice", "concept_ids": ["MATH_COMPLEX"],
        "difficulty": 0.35, "discrimination": 0.45, "ability": "understand",
        "stem": "复数 z=(1+i)/(1-i)（i 为虚数单位）等于（　）",
        "options": {"A": "1", "B": "i", "C": "-i", "D": "-1"},
        "answer": "B",
        "solution_steps": [
            "复数除法：分子分母同乘分母的共轭 (1+i)。",
            "z=(1+i)(1+i)/[(1-i)(1+i)]=(1+i)²/(1-i²)=(1+2i+i²)/(1-(-1))=2i/2=i，选 B。"],
        "socratic_questions": [
            "复数除法要消去分母的虚部，常用什么技巧？",
            "分母 (1-i) 的共轭复数是什么？",
            "计算中 i² 等于多少？别忘了这一步。"],
        "common_errors": ["把 i² 当成 1（应为 -1）", "忘记分子分母同乘共轭"],
        "source": "自编",
    },
]
