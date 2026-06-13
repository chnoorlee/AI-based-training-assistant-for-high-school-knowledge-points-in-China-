<script setup>
import { ref, onMounted } from 'vue'
const seed = ref('M0002')
const count = ref(3)
const queue = ref([])
const lastGen = ref([])
const busy = ref(false)
const note = ref('')
import { api } from '../api.js'

async function loadQueue() { queue.value = await api.variantQueue().catch(() => []) }
onMounted(loadQueue)

async function generate() {
  busy.value = true; note.value = ''
  try {
    lastGen.value = await api.variantGenerate({ user_id: 'teacher', problem_id: seed.value, count: Number(count.value) })
    await loadQueue()
  } catch (e) {
    note.value = e.status === 403 ? ('已熔断：' + (e.detail?.reason || '高考期间不可生成')) : ('失败：' + e.message)
  } finally { busy.value = false }
}

async function review(v, approve) {
  await api.variantReview(v.id, { reviewer: '王老师', approve, note: approve ? '参数合理，准予入库' : '情境欠妥，驳回' })
  await loadQueue()
}
</script>

<template>
  <div class="grid" style="gap:16px">
    <div class="card">
      <h3>✦ 生成变式题（参数化模板 + 符号求解，保证数学正确）</h3>
      <div class="row">
        <label class="muted">种子题号</label>
        <input v-model="seed" style="width:120px" placeholder="如 M0002 / P0001 / B0001" />
        <label class="muted">数量</label>
        <input v-model="count" type="number" min="1" max="6" style="width:70px" />
        <button class="btn" :disabled="busy" @click="generate">生成</button>
        <span v-if="note" class="pill bad">{{ note }}</span>
      </div>
      <div v-if="lastGen.length" class="hint" style="margin-top:8px">
        本次生成 {{ lastGen.length }} 道，通过自动质检 {{ lastGen.filter(v=>v.review_status==='pending').length }} 道进入审核队列。
      </div>
    </div>

    <div class="card">
      <h3>👩‍🏫 人工审核队列 <span class="pill muted">{{ queue.length }} 待审</span></h3>
      <div v-if="queue.length===0" class="empty">队列为空。先在上方生成变式题。</div>
      <div v-for="v in queue" :key="v.id" class="card" style="box-shadow:none;background:#fafbff;margin-bottom:12px">
        <div class="row" style="justify-content:space-between">
          <div class="mono muted" style="font-size:12px">{{ v.id }} · 模板 {{ v.template_id }} <span v-if="v.scenario_category" class="tag">{{ v.scenario_category }}</span></div>
          <div class="row">
            <button class="btn good sm" @click="review(v, true)">通过</button>
            <button class="btn bad sm" @click="review(v, false)">驳回</button>
          </div>
        </div>
        <div style="margin:8px 0;line-height:1.6">{{ v.problem.stem }}</div>
        <div v-if="Object.keys(v.problem.options||{}).length" class="muted" style="font-size:13px;margin-bottom:6px">
          <span v-for="(t,k) in v.problem.options" :key="k" style="margin-right:14px">{{ k }}. {{ t }}</span>
        </div>
        <div class="row" style="gap:14px;font-size:12px">
          <span>✅ 答案：<b>{{ v.problem.answer }}</b></span>
          <span class="muted">预测难度 {{ v.quality.predicted_difficulty }}</span>
          <span class="muted">区分度 {{ v.quality.predicted_discrimination }}</span>
          <span class="pill" :class="v.quality.copyright_similarity<=0.3 ? 'ok':'bad'">版权相似 {{ v.quality.copyright_similarity }}</span>
          <span class="pill" :class="v.quality.rule_passed ? 'ok':'bad'">规则{{ v.quality.rule_passed?'通过':'未过' }}</span>
          <span class="pill" :class="v.quality.content_safe ? 'ok':'bad'">内容{{ v.quality.content_safe?'安全':'风险' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
