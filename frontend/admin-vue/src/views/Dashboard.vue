<script setup>
import { ref, onMounted } from 'vue'
import { api, SUBJECT_CN } from '../api.js'

const subjects = ref([])
const alerts = ref({ snapshot: {}, alerts: [] })
const ab = ref(null)
const drift = ref(null)
const loading = ref(true)

async function load() {
  loading.value = true
  const safe = (p) => p.catch(() => null)
  const [s, a, b, d] = await Promise.all([
    safe(api.subjects()), safe(api.alerts()), safe(api.abStatus()), safe(api.drift(24)),
  ])
  subjects.value = s?.subjects || []
  alerts.value = a || { snapshot: {}, alerts: [] }
  ab.value = b
  drift.value = d
  loading.value = false
}
onMounted(load)

const totalProblems = () => subjects.value.reduce((n, s) => n + s.problems, 0)
const totalConcepts = () => subjects.value.reduce((n, s) => n + s.concepts, 0)
const sev = (s) => ({ none: 'ok', minor: 'warn', major: 'bad' }[s] || 'muted')
const alertClass = (s) => ({ info: 'muted', warning: 'warn', critical: 'bad' }[s] || 'muted')
</script>

<template>
  <div class="grid" style="gap:16px">
    <div class="row" style="justify-content:space-between">
      <div class="section-title" style="margin:0">系统总览</div>
      <button class="btn ghost sm" @click="load">⟳ 刷新</button>
    </div>

    <div class="grid cols-4">
      <div class="card"><div class="kpi">{{ subjects.length }}</div><div class="kpi-label">已接入学科</div></div>
      <div class="card"><div class="kpi">{{ totalConcepts() }}</div><div class="kpi-label">知识点（统一图谱）</div></div>
      <div class="card"><div class="kpi">{{ totalProblems() }}</div><div class="kpi-label">题库题目</div></div>
      <div class="card">
        <div class="kpi">{{ alerts.snapshot.total ?? 0 }}</div>
        <div class="kpi-label">诊断服务调用量</div>
      </div>
    </div>

    <div class="card">
      <h3>📚 学科与知识图谱</h3>
      <div class="grid cols-4">
        <div v-for="s in subjects" :key="s.subject" class="card" style="box-shadow:none;background:#fafbff">
          <div style="font-weight:700">{{ SUBJECT_CN[s.subject] || s.subject }}</div>
          <div class="muted" style="font-size:12px;margin:4px 0 8px">
            {{ s.concepts }} 知识点 · {{ s.problems }} 题
          </div>
          <div class="row" style="gap:4px">
            <span v-for="m in s.modules.slice(0,4)" :key="m" class="tag">{{ m }}</span>
            <span v-if="s.modules.length>4" class="muted" style="font-size:11px">+{{ s.modules.length-4 }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>📈 模型监控 · 告警</h3>
        <div class="row" style="gap:22px;margin-bottom:10px">
          <div><div class="kpi" style="font-size:20px">{{ (alerts.snapshot.latency_p95 ?? 0).toFixed(0) }}ms</div><div class="kpi-label">p95 时延</div></div>
          <div><div class="kpi" style="font-size:20px">{{ ((alerts.snapshot.error_rate ?? 0)*100).toFixed(1) }}%</div><div class="kpi-label">错误率</div></div>
          <div><div class="kpi" style="font-size:20px">{{ alerts.snapshot.pred_mean != null ? alerts.snapshot.pred_mean.toFixed(2) : '—' }}</div><div class="kpi-label">预测均值</div></div>
        </div>
        <div v-if="alerts.snapshot.by_bucket && Object.keys(alerts.snapshot.by_bucket).length" class="muted" style="font-size:12px;margin-bottom:8px">
          灰度分桶：<span v-for="(v,k) in alerts.snapshot.by_bucket" :key="k" class="tag">{{ k }} {{ v }}</span>
        </div>
        <div v-if="alerts.alerts.length===0" class="pill ok">无告警 · 指标健康</div>
        <div v-for="a in alerts.alerts" :key="a.name" class="row" style="margin-top:6px">
          <span class="pill" :class="alertClass(a.severity)">{{ a.severity }}</span>
          <span style="font-size:13px">{{ a.message }}</span>
        </div>
        <div v-if="(alerts.snapshot.total ?? 0)===0" class="hint" style="margin-top:8px">提示：进入「学情诊断」生成示例数据后，监控指标会填充。</div>
      </div>

      <div class="card">
        <h3>🧪 A/B 灰度发布</h3>
        <template v-if="ab">
          <div class="row" style="margin-bottom:8px">
            <span class="pill" :class="ab.decision==='promote'?'ok':(ab.decision==='rollback'?'bad':'muted')">
              {{ {promote:'建议全量', rollback:'建议回滚', hold:'继续观察'}[ab.decision] || ab.decision }}
            </span>
            <span class="muted" style="font-size:12px">{{ ab.reason }}</span>
          </div>
          <table>
            <tr><th>桶</th><th>样本</th><th>准确率</th><th>AUC</th></tr>
            <tr><td>冠军</td><td>{{ ab.champion.n }}</td><td>{{ ab.champion.accuracy?.toFixed?.(3) ?? '—' }}</td><td>{{ ab.champion.auc?.toFixed?.(3) ?? '—' }}</td></tr>
            <tr><td>挑战者</td><td>{{ ab.canary.n }}</td><td>{{ ab.canary.accuracy?.toFixed?.(3) ?? '—' }}</td><td>{{ ab.canary.auc?.toFixed?.(3) ?? '—' }}</td></tr>
          </table>
          <div class="hint" style="margin-top:8px">灰度比例 {{ ab.config?.canary_pct ?? 0 }}% · {{ ab.config?.enabled ? '已启用' : '未启用挑战者' }}</div>
        </template>
        <div v-else class="empty">A/B 状态不可用</div>
      </div>
    </div>

    <div class="card">
      <h3>🌊 数据/标签漂移检测（PSI · 近 24h vs 之前）</h3>
      <template v-if="drift">
        <div class="row" style="margin-bottom:10px">
          整体严重度：<span class="pill" :class="sev(drift.overall_severity)">{{ drift.overall_severity }}</span>
          <span class="muted" style="font-size:12px">参考窗 {{ drift.n_ref }} · 当前窗 {{ drift.n_cur }}</span>
        </div>
        <table>
          <tr><th>特征</th><th>PSI</th><th>严重度</th></tr>
          <tr v-for="(v,k) in drift.features" :key="k">
            <td>{{ k }}</td><td class="mono">{{ v.psi }}</td>
            <td><span class="pill" :class="sev(v.severity)">{{ v.severity }}</span></td>
          </tr>
          <tr><td>label(correctness)</td><td class="mono">{{ drift.label_psi }}</td>
            <td><span class="pill" :class="sev(drift.label_severity)">{{ drift.label_severity }}</span></td></tr>
        </table>
      </template>
      <div v-else class="empty">漂移报告不可用</div>
    </div>
  </div>
</template>
