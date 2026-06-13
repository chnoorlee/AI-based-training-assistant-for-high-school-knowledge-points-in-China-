<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const uid = ref('student_demo')
const queue = ref([])
const stats = ref(null)
const forecast = ref(null)
const busy = ref(false)
const msg = ref('')

const WRONG = ['M0002', 'M0003', 'P0001', 'C0004', 'B0001']

async function loadAll() {
  const safe = (p) => p.catch(() => null)
  const [q, s, f] = await Promise.all([
    safe(api.reviewQueue(uid.value)), safe(api.reviewStats(uid.value)), safe(api.reviewForecast(uid.value)),
  ])
  queue.value = q?.items || []
  stats.value = s
  forecast.value = f
}
onMounted(loadAll)

async function seedWrong() {
  busy.value = true; msg.value = '写入错题…'
  try {
    for (const pid of WRONG) await api.answer({ user_id: uid.value, problem_id: pid, correct: false, time_spent_s: 100 })
    msg.value = '已写入 5 道错题（自动入册并排程）'
    await loadAll()
  } finally { busy.value = false }
}

async function grade(pid, correct) {
  await api.reviewGrade({ user_id: uid.value, problem_id: pid, correct, time_spent_s: correct ? 40 : 120 })
  await loadAll()
}

const maxForecast = () => Math.max(1, ...((forecast.value?.days || []).map(d => d.count)))
const statusCn = { learning: '学习中', review: '复习中', graduated: '已掌握' }
</script>

<template>
  <div class="grid" style="gap:16px">
    <div class="card">
      <div class="row" style="justify-content:space-between">
        <div class="row">
          <label class="muted">学生</label><input v-model="uid" style="width:160px" />
          <button class="btn" :disabled="busy" @click="loadAll">查询</button>
          <button class="btn ghost" :disabled="busy" @click="seedWrong">生成示例错题</button>
        </div>
        <span class="muted">{{ msg }}</span>
      </div>
    </div>

    <div class="grid cols-4" v-if="stats">
      <div class="card"><div class="kpi">{{ stats.total }}</div><div class="kpi-label">错题总数</div></div>
      <div class="card"><div class="kpi" style="color:var(--bad)">{{ stats.due_now }}</div><div class="kpi-label">今日待复习</div></div>
      <div class="card"><div class="kpi" style="color:var(--good)">{{ stats.graduated }}</div><div class="kpi-label">已掌握</div></div>
      <div class="card"><div class="kpi">{{ Math.round((stats.avg_retention||0)*100) }}%</div><div class="kpi-label">平均记忆保持率</div></div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>↻ 今日复习队列（按遗忘紧迫度排序）</h3>
        <div v-if="queue.length===0" class="empty">暂无到期错题。点「生成示例错题」体验。</div>
        <table v-else>
          <tr><th>题号</th><th>状态</th><th>保持率</th><th>间隔</th><th>操作</th></tr>
          <tr v-for="it in queue" :key="it.problem_id">
            <td class="mono">{{ it.problem_id }}</td>
            <td><span class="pill" :class="it.status==='learning'?'warn':'muted'">{{ statusCn[it.status]||it.status }}</span></td>
            <td><span :style="{color: it.retention<0.6 ? 'var(--bad)':'var(--ink)'}">{{ Math.round(it.retention*100) }}%</span></td>
            <td class="muted">{{ it.interval_days }}天</td>
            <td class="row">
              <button class="btn good sm" @click="grade(it.problem_id, true)">答对</button>
              <button class="btn bad sm" @click="grade(it.problem_id, false)">答错</button>
            </td>
          </tr>
        </table>
      </div>

      <div class="card">
        <h3>📅 未来 7 天复习预测</h3>
        <div v-if="forecast">
          <div class="muted" style="margin-bottom:8px">逾期 {{ forecast.overdue }} 题</div>
          <div v-for="d in forecast.days" :key="d.date" class="row" style="margin-bottom:6px">
            <span class="mono muted" style="width:88px;font-size:12px">{{ d.date.slice(5) }}</span>
            <div class="bar-track" style="flex:1">
              <div class="bar-fill" :style="{ width: (d.count/maxForecast()*100)+'%' }"></div>
            </div>
            <span style="width:28px;text-align:right">{{ d.count }}</span>
          </div>
        </div>
        <div v-else class="empty">预测不可用</div>
      </div>
    </div>
  </div>
</template>
