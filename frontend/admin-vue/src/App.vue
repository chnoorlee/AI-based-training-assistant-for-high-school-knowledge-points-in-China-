<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './api.js'

const route = useRoute()
const health = ref(null)
const err = ref(false)
const nav = [
  { to: '/dashboard', label: '概览', ico: '▥' },
  { to: '/diagnosis', label: '学情诊断', ico: '◎' },
  { to: '/plan', label: '提分规划', ico: '◷' },
  { to: '/variant', label: '变式题审核', ico: '✦' },
  { to: '/review', label: '错题复习', ico: '↻' },
]

onMounted(async () => {
  try { health.value = await api.health() } catch { err.value = true }
})
</script>

<template>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">智考通<small>基于认知诊断 · 管理后台</small></div>
      <nav class="nav">
        <router-link v-for="n in nav" :key="n.to" :to="n.to"
          :class="{ active: route.path === n.to }">
          <span class="ico">{{ n.ico }}</span>{{ n.label }}
        </router-link>
      </nav>
      <div class="foot">
        <div v-if="health">● 后端在线 · {{ health.problems }} 题 / {{ health.concepts }} 知识点</div>
        <div v-else-if="err" style="color:#f87171">● 后端未连接（请启动 uvicorn）</div>
        <div v-else>● 连接中…</div>
        <div style="margin-top:6px">不押题 · 绝不直接给答案 · 高考熔断</div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <h1>{{ route.name || '管理后台' }}</h1>
        <div class="row">
          <span class="pill" :class="health ? 'ok' : 'bad'">
            {{ health ? 'API 正常' : 'API 离线' }}
          </span>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>
