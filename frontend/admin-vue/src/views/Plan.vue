<script setup>
import { computed, ref } from 'vue'
import { api, SUBJECT_CN } from '../api.js'

const uid = ref('student_demo')
const daily = ref(120)
const subject = ref('')
const plan = ref(null)
const exec = ref(null)           // 题型级丢分归因报告（有分题型数据时）
const busy = ref(false)
const msg = ref('提示：先到「学情诊断」为该学生生成作答，规划会更精准。')
const mock = ref({ math: '', physics: '', chemistry: '', biology: '' })
const mockMsg = ref('')
const showSec = ref(false)
const secSubject = ref('math')
const paper = ref({})            // {subject: [{id,name,points,tier,...}]}
const secInput = ref({})         // {subject: {section_id: ''}}

// 全科「会做却丢」(易/中可挽回) 与总丢分汇总
const fixableTotal = computed(() =>
  (exec.value?.subjects || []).reduce((a, s) => a + (s.fixable_loss || 0), 0).toFixed(1))
const lossTotal = computed(() =>
  (exec.value?.subjects || []).reduce((a, s) => a + (s.total_loss || 0), 0).toFixed(1))

const run = async () => {
  busy.value = true; msg.value = ''
  try {
    const [p, ex] = await Promise.all([
      api.plan({ user_id: uid.value, daily_minutes: Number(daily.value), subject: subject.value }),
      api.execution(uid.value).catch(() => null),
    ])
    plan.value = p
    exec.value = (ex && ex.has_section_data) ? ex : null
  } catch (e) { msg.value = '失败：' + (e.detail?.reason || e.message); plan.value = null }
  finally { busy.value = false }
}

const toggleSec = async () => {
  showSec.value = !showSec.value
  if (showSec.value && !Object.keys(paper.value).length) {
    try { paper.value = await api.examPaper() } catch { /* 卷面结构可选 */ }
  }
}
const setSec = (subj, sid, val) => {
  secInput.value = { ...secInput.value, [subj]: { ...(secInput.value[subj] || {}), [sid]: val } }
}

const submitMock = async () => {
  const scores = {}
  for (const [k, v] of Object.entries(mock.value)) if (v !== '' && v != null) scores[k] = Number(v)
  if (!Object.keys(scores).length) { mockMsg.value = '请至少填一科分数'; return }
  const section_scores = {}
  for (const [subj, secs] of Object.entries(secInput.value)) {
    const got = {}
    for (const [sid, v] of Object.entries(secs)) if (v !== '' && v != null) got[sid] = Number(v)
    if (Object.keys(got).length) section_scores[subj] = got
  }
  mockMsg.value = '提交中…'
  try {
    const body = { user_id: uid.value, exam_name: '模考', scores }
    if (Object.keys(section_scores).length) body.section_scores = section_scores
    await api.submitMock(body)
    mockMsg.value = '已录入并校准，正在重排计划…'
    await run()
    mockMsg.value = Object.keys(section_scores).length
      ? '✓ 已按分题型得分定位应试丢分，限时训练已排进每日计划'
      : '✓ 计划已按真实模考反馈更新'
  } catch (e) { mockMsg.value = '失败：' + (e.detail?.reason || e.message) }
}
const TIER = { 易: 'ok', 中: 'warn', 难: 'bad', 压轴: 'bad' }
const SUBS = [['math', '数学'], ['physics', '物理'], ['chemistry', '化学'], ['biology', '生物']]
</script>

<template>
  <div class="grid" style="gap:16px">
    <div class="card">
      <div class="row">
        <label class="muted">学生</label><input v-model="uid" style="width:150px" />
        <label class="muted">每日(分钟)</label><input v-model="daily" type="number" style="width:90px" />
        <label class="muted">学科</label>
        <select v-model="subject">
          <option value="">全科</option>
          <option v-for="(cn,k) in SUBJECT_CN" :key="k" :value="k">{{ cn }}</option>
        </select>
        <button class="btn" :disabled="busy" @click="run">{{ busy ? '规划中…' : '生成提分计划' }}</button>
        <span v-if="msg" class="muted">{{ msg }}</span>
      </div>
    </div>

    <template v-if="plan">
      <div class="grid cols-4">
        <div class="card"><div class="kpi" style="color:var(--bad)">{{ plan.days_left }}</div><div class="kpi-label">距高考(天)</div></div>
        <div class="card"><div class="kpi">{{ Math.round(plan.total_study_minutes/60) }}h</div><div class="kpi-label">计划总投入</div></div>
        <div class="card"><div class="kpi" style="color:var(--good)">+{{ plan.expected_score_gain }}</div><div class="kpi-label">预计提分（估计）</div></div>
        <div class="card"><div class="kpi">{{ plan.daily_minutes }}min</div><div class="kpi-label">每日时长</div></div>
      </div>
      <div class="grid cols-2">
        <div class="card" style="background:#eef2ff;border-color:#c7d2fe">
          <h3>🎯 模考估分 <span class="pill" :class="plan.mock_calibrated ? 'ok' : 'muted'">
            {{ plan.mock_calibrated ? '已用真实模考校准' : '待模考校准' }}</span></h3>
          <div class="kpi">{{ plan.projected_score_now }}<span class="muted" style="font-size:14px"> / {{ plan.projected_full }} 分</span></div>
          <div v-if="plan.feedback_note" style="margin-top:8px;font-size:13px;color:var(--accent)">↳ {{ plan.feedback_note }}</div>
          <div style="margin-top:6px;font-size:12px" class="muted">{{ plan.projected_note }}</div>
        </div>
        <div class="card">
          <h3>📥 录入真实模考成绩（作为反馈信号）</h3>
          <div class="row" style="gap:8px">
            <template v-for="[k,cn] in SUBS" :key="k">
              <label class="muted">{{ cn }}</label>
              <input v-model="mock[k]" type="number" min="0" placeholder="—" style="width:64px" />
            </template>
            <button class="btn good sm" @click="submitMock">提交并重排</button>
          </div>
          <div style="margin-top:10px">
            <a class="muted" style="cursor:pointer;user-select:none" @click="toggleSec">
              {{ showSec ? '▾' : '▸' }} ✏️ 按题型录入（定位选择/压轴丢分 → 开限时训练）</a>
            <div v-if="showSec" style="margin-top:8px">
              <div class="row" style="gap:6px;margin-bottom:6px">
                <label class="muted">科目</label>
                <select v-model="secSubject">
                  <option v-for="[k,cn] in SUBS" :key="k" :value="k">{{ cn }}</option>
                </select>
                <span class="muted" style="font-size:12px">填了哪几类题就分析哪几类</span>
              </div>
              <div class="row" style="gap:10px;flex-wrap:wrap">
                <span v-for="sec in (paper[secSubject]||[])" :key="sec.id"
                  style="display:inline-flex;align-items:center;gap:4px">
                  <span class="muted" style="font-size:12px">{{ sec.name }}<i style="opacity:.6">/{{ sec.points }}</i></span>
                  <input type="number" placeholder="—" style="width:52px" min="0" :max="sec.points"
                    :value="(secInput[secSubject]||{})[sec.id] ?? ''"
                    @input="setSec(secSubject, sec.id, $event.target.value)" />
                </span>
              </div>
            </div>
          </div>
          <div v-if="mockMsg" class="muted" style="margin-top:8px">{{ mockMsg }}</div>
          <div class="hint" style="margin-top:6px">模型会比对预测与真实分：识别「会做却失分」、校准估分、把时间投向考场上最该补的科目。</div>
        </div>
      </div>

      <div v-if="exec" class="card" style="background:#fffbeb;border-color:#fde68a">
        <h3>🔍 题型级丢分归因（按你的水平「该拿多少」对照真实得分）</h3>
        <div class="row" style="gap:16px;margin:2px 0 10px">
          <div><span class="kpi" style="font-size:22px;color:var(--bad)">{{ lossTotal }}</span>
            <span class="muted" style="font-size:12px"> 分 总丢分</span></div>
          <div><span class="kpi" style="font-size:22px;color:var(--good)">{{ fixableTotal }}</span>
            <span class="muted" style="font-size:12px"> 分 「会做却丢」(易/中档，最该补回)</span></div>
        </div>
        <div v-for="se in exec.subjects" :key="se.subject" style="margin-bottom:10px">
          <b style="font-size:13px">{{ SUBJECT_CN[se.subject] || se.subject }}</b>
          <span class="muted" style="font-size:12px"> 丢 {{ se.total_loss }} 分（其中易/中可挽回 {{ se.fixable_loss }} 分）</span>
          <table style="margin-top:4px">
            <tr><th>题型</th><th>难易</th><th>应得</th><th>实得</th><th>丢分</th><th>主因</th></tr>
            <tr v-for="s in se.sections" :key="s.section_id" :style="{opacity: s.got==null ? .45 : 1}">
              <td>{{ s.name }}</td>
              <td><span class="pill" :class="TIER[s.tier]">{{ s.tier }}</span></td>
              <td class="mono">{{ s.expected }}</td>
              <td class="mono">{{ s.got == null ? '—' : s.got }}</td>
              <td :style="{color: s.loss>0 ? 'var(--bad)' : 'var(--muted)', fontWeight: s.loss>0?700:400}">
                {{ s.loss > 0 ? s.loss : '·' }}</td>
              <td class="muted" style="font-size:12px">{{ s.loss > 0 ? s.cause : '' }}</td>
            </tr>
          </table>
        </div>
        <div class="hint">「应得」= 按你各模块掌握度，这类题正常该拿的分；丢分 = 应得−实得，即「会做却没拿到」。下方限时训练就照此开方。</div>
      </div>

      <div v-if="plan.timed_drills && plan.timed_drills.length" class="card"
        style="background:#fff7ed;border-color:#fed7aa">
        <h3>⏱ 应试丢分 → 限时训练（按可挽回分排序，已排进每日首项）</h3>
        <table>
          <tr><th>限时训练</th><th>难易</th><th>量/限时</th><th>目标</th><th>针对</th><th>可挽回</th></tr>
          <tr v-for="(d,i) in plan.timed_drills" :key="i">
            <td>{{ d.title }}</td>
            <td><span class="pill" :class="TIER[d.tier]">{{ d.tier }}</span></td>
            <td class="muted">{{ d.n_problems }}题/{{ d.time_limit_min }}min</td>
            <td style="font-size:12px">{{ d.goal }}</td>
            <td class="muted" style="font-size:12px">{{ d.cause }}</td>
            <td style="color:var(--good);font-weight:700">+{{ d.recoverable_points }}</td>
          </tr>
        </table>
        <div class="hint" style="margin-top:6px">压轴以「抢前两步的分」为主，易/中档以「稳拿+不手滑」为主——不是多做题，而是练对地方。</div>
      </div>

      <div class="card">
        <h3>① 提分性价比排序（先补这些，分/小时最高）</h3>
        <table>
          <tr><th>考点</th><th>科</th><th>掌握</th><th>高考分</th><th>难易</th><th>性价比(分/h)</th><th>投入</th><th>预计提分</th></tr>
          <tr v-for="it in plan.priorities" :key="it.concept_id">
            <td>{{ it.concept_name }}</td>
            <td><span class="tag">{{ SUBJECT_CN[it.subject] }}</span></td>
            <td><span :style="{color: it.mastery<0.4?'var(--bad)':'var(--ink)'}">{{ Math.round(it.mastery*100) }}%</span></td>
            <td>{{ it.exam_weight }}</td>
            <td><span class="pill" :class="TIER[it.learnability]">{{ it.learnability }}</span></td>
            <td class="mono">{{ it.roi.toFixed(1) }}</td>
            <td class="muted">{{ it.allocated_minutes }}min</td>
            <td style="color:var(--good);font-weight:700">+{{ it.expected_gain }}</td>
          </tr>
        </table>
      </div>

      <div class="card">
        <h3>② 每日计划（跨学科交错 + 错题复习；🔒 熔断日仅复习）</h3>
        <div class="grid cols-2">
          <div v-for="d in plan.days" :key="d.day_index" class="card"
            :style="{ boxShadow:'none', background: d.is_blackout ? '#fef2f2' : '#fafbff', borderColor: d.is_blackout ? '#fecaca' : '#eef2f7' }">
            <div class="row" style="justify-content:space-between">
              <b>第{{ d.day_index+1 }}天 · {{ d.date.slice(5) }}</b>
              <span class="muted" style="font-size:12px">{{ d.total_minutes }}min {{ d.is_blackout ? '🔒熔断' : '' }}</span>
            </div>
            <div v-for="(t,i) in d.tasks" :key="i" style="margin-top:6px;font-size:13px">
              <span v-if="t.kind==='timed_drill'" style="color:#c2410c">⏱ <b>{{ t.concept_name }}</b>
                <span class="muted"> {{ t.minutes }}min / {{ t.n_problems }}题</span></span>
              <span v-else-if="t.kind==='learn'">📘 攻坚 <b>{{ SUBJECT_CN[t.subject]||t.subject }}·{{ t.concept_name }}</b>
                <span class="muted"> {{ t.minutes }}min / {{ t.n_problems }}题</span></span>
              <span v-else class="muted">↻ {{ t.detail }}（{{ t.minutes }}min）</span>
            </div>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="card empty">输入学生与每日时长，点「生成提分计划」。</div>
  </div>
</template>
