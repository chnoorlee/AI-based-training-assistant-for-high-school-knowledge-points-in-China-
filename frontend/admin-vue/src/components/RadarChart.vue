<script setup>
import { computed } from 'vue'

// props.axes: [{ label, value(0~1) }]
const props = defineProps({
  axes: { type: Array, default: () => [] },
  size: { type: Number, default: 280 },
})

const cx = computed(() => props.size / 2)
const r = computed(() => props.size / 2 - 38)

function point(i, frac) {
  const n = props.axes.length || 1
  const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n
  return [cx.value + r.value * frac * Math.cos(ang), cx.value + r.value * frac * Math.sin(ang)]
}
const rings = [0.25, 0.5, 0.75, 1]
const gridPolys = computed(() =>
  rings.map((rr) => props.axes.map((_, i) => point(i, rr).join(',')).join(' ')))
const dataPoly = computed(() =>
  props.axes.map((a, i) => point(i, Math.max(0.02, a.value)).join(',')).join(' '))
const labels = computed(() =>
  props.axes.map((a, i) => {
    const [x, y] = point(i, 1.16)
    return { x, y, label: a.label, value: a.value }
  }))
</script>

<template>
  <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
    <polygon v-for="(g, i) in gridPolys" :key="i" :points="g"
      fill="none" stroke="#e5e7eb" stroke-width="1" />
    <line v-for="(a, i) in axes" :key="'l' + i"
      :x1="cx" :y1="cx" :x2="point(i, 1)[0]" :y2="point(i, 1)[1]" stroke="#eef2f7" />
    <polygon :points="dataPoly" fill="rgba(79,70,229,0.18)" stroke="#4f46e5" stroke-width="2" />
    <circle v-for="(a, i) in axes" :key="'c' + i"
      :cx="point(i, Math.max(0.02, a.value))[0]" :cy="point(i, Math.max(0.02, a.value))[1]"
      r="3" fill="#4f46e5" />
    <text v-for="(t, i) in labels" :key="'t' + i" :x="t.x" :y="t.y"
      text-anchor="middle" font-size="11" fill="#6b7280">
      {{ t.label }}
      <tspan :x="t.x" dy="13" font-size="10" :fill="t.value < 0.5 ? '#dc2626' : '#16a34a'">
        {{ Math.round(t.value * 100) }}%
      </tspan>
    </text>
  </svg>
</template>
