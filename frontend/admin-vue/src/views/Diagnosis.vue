<script setup>
import { ref, computed } from 'vue'
import { api, SUBJECT_CN } from '../api.js'
import RadarChart from '../components/RadarChart.vue'

const uid = ref('student_demo')
const subject = ref('')
const report = ref(null)
const recs = ref([])
const busy = ref(false)
const msg = ref('')

const SAMPLE = [
  ['M0001', true], ['M0002', false], ['M0003', false], ['M0006', true],
  ['P0001', false], ['P0002', true], ['P0004', false],
  ['C0001', true], ['C0004', false],
  ['B0001', false], ['B0003', true],
]
const ERR_CN = { concept: '概念误解', calculation: '计算失误', misread: '审题失误', logic: '逻辑混乱', time: '时间管理' }
const ABILITY_CN = { memory: '记忆', understand: '理解', apply: '应用', analyze: '分析', synthesize: '综合', create: '创新' }

async function seed() {
  busy.value = true; msg.value = '正在写入示例作答…'
  try {
    for (const [pid, ok] of SAMPLE) {
      await api.answer({ user_id: uid.value, problem_id: pid, correct: ok, time_spent_s: ok ? 45 : 110 })
    }
    msg.value = '示例数据已写入，开始诊断…'
    await run()
  } catch (e) { msg.value = '失败：' + e.message } finally { busy.value = false }
}

async function run() {
  busy.value = true; msg.value = ''
  try {
    report.value = await api.diagnosis(uid.value, subject.value)
    recs.value = (await api.recommend(uid.value, subject.value, 6)).items
  } catch (e) { msg.value = '诊断失败：' + (e.detail?.reason || e.message); report.value = null }
  finally { busy.value = false }
}

const weak = computed(() => {
  if (!report.value) return []
  const map = Object.fromEntries(report.value.concept_mastery.map((c) => [c.concept_id, c]))
  return report.value.weak_concepts.map((id) => map[id]).filter(Boolean).slice(0, 6)
})
const lvlCn = { unmastered: '未掌握', initial: '初步掌握', basic: '基本掌握', proficient: '熟练掌握' }
const reasonCn = { weakness: '强化', consolidate: '巩固', stretch: '提高' }
</script>

<template>
  <div class="grid" style="gap:16px">
    <div class="card">
      <div class="row" style="justify-content:space-between">
        <div class="row">
          <label class="muted">学生</label>
          <input v-model="uid" style="width:160px" />
          <label class="muted">学科</label>
          <select v-model="subject">
            <option value="">综合</option>
            <option v-for="(cn,k) in SUBJECT_CN" :key="k" :value="k">{{ cn }}</option>
          </select>
          <button class="btn" :disabled="busy" @click="run">诊断</button>
          <button class="btn ghost" :disabled="busy" @click="seed">生成示例数据并诊断</button>
        </div>
        <span v-if="msg" class="muted">{{ msg }}</span>
      </div>
    </div>

    <div v-if="report" class="grid cols-2">
      <div class="card">
        <h3>🧭 能力雷达图（{{ subject ? SUBJECT_CN[subject] : '综合' }}）</h3>
        <div style="display:flex;justify-content:center">
          <RadarChart :axes="report.radar.map(r => ({ label: r.module, value: r.score }))" :size="320" />
        </div>
        <div class="row" style="justify-content:center;margin-top:6px">
          <span class="muted">整体掌握度</span>
          <span class="kpi" style="font-size:20px">{{ Math.round(report.overall_mastery*100) }}%</span>
          <span class="muted">· {{ report.n_responses }} 条作答</span>
        </div>
      </div>

      <div class="card">
        <h3>⚠️ 薄弱知识点（优先突破）</h3>
        <div v-if="weak.length===0" class="empty">暂无明显薄弱点</div>
        <div v-for="c in weak" :key="c.concept_id" style="margin-bottom:11px">
          <div class="row" style="justify-content:space-between">
            <span>{{ c.concept_name }}</span>
            <span class="muted" style="font-size:12px">{{ lvlCn[c.level] || c.level }} · 预测答对 {{ Math.round(c.predicted_correct_prob*100) }}%</span>
          </div>
          <div class="bar-track" style="margin-top:4px">
            <div class="bar-fill" :style="{ width: (c.score*100)+'%', background: c.score<0.4 ? '#dc2626' : '#d97706' }"></div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>🔎 错误类型画像</h3>
        <div v-if="Object.keys(report.error_profile).length===0" class="empty">暂无错误数据</div>
        <div v-for="(v,k) in report.error_profile" :key="k" style="margin-bottom:9px">
          <div class="row" style="justify-content:space-between"><span>{{ ERR_CN[k]||k }}</span><span class="muted">{{ Math.round(v*100) }}%</span></div>
          <div class="bar-track" style="margin-top:3px"><div class="bar-fill" :style="{ width:(v*100)+'%', background:'#dc2626' }"></div></div>
        </div>
        <h3 style="margin-top:14px">🎯 能力层级画像</h3>
        <div v-for="(v,k) in report.ability_profile" :key="k" style="margin-bottom:8px">
          <div class="row" style="justify-content:space-between"><span>{{ ABILITY_CN[k]||k }}</span><span class="muted">{{ Math.round(v*100) }}%</span></div>
          <div class="bar-track" style="margin-top:3px"><div class="bar-fill" :style="{ width:(v*100)+'%' }"></div></div>
        </div>
      </div>

      <div class="card">
        <h3>📝 诊断解读 + 自适应推荐</h3>
        <p style="line-height:1.7;margin:0 0 12px">{{ report.explanation }}</p>
        <div class="section-title">推荐练习（ZPD · 70/20/10）</div>
        <table>
          <tr><th>题号</th><th>类型</th><th>预测答对率</th><th>说明</th></tr>
          <tr v-for="it in recs" :key="it.problem_id">
            <td class="mono">{{ it.problem_id }}</td>
            <td><span class="pill muted">{{ reasonCn[it.reason]||it.reason }}</span></td>
            <td>{{ Math.round(it.predicted_correct_prob*100) }}%</td>
            <td class="muted" style="font-size:12px">{{ it.rationale }}</td>
          </tr>
        </table>
      </div>
    </div>

    <div v-else class="card empty">输入学生 ID 后点「生成示例数据并诊断」，或对已有学生点「诊断」。</div>
  </div>
</template>
