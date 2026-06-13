import React, { useState, useEffect } from 'react'
import { View, Text, ScrollView, TouchableOpacity, StyleSheet } from 'react-native'
import { api, USER } from '../api'
import { colors } from '../theme'

const STATUS = { learning: '学习中', review: '复习中', graduated: '已掌握' }

export default function ReviewScreen() {
  const [queue, setQueue] = useState([])
  const [stats, setStats] = useState(null)
  const [msg, setMsg] = useState('')

  const load = async () => {
    try {
      const [q, st] = await Promise.all([api.reviewQueue(USER), api.reviewStats(USER)])
      setQueue(q.items); setStats(st)
      if (!q.items.length) setMsg('暂无到期错题（先在「诊断」页生成作答会自动入册）')
      else setMsg('')
    } catch (e) { setMsg('失败：' + e.message) }
  }
  useEffect(() => { load() }, [])

  const grade = async (pid, correct) => {
    await api.reviewGrade({ user_id: USER, problem_id: pid, correct, time_spent_s: correct ? 40 : 120 })
    await load()
  }

  return (
    <ScrollView style={s.page} contentContainerStyle={{ padding: 14 }}>
      {stats && (
        <View style={s.kpis}>
          {[['错题', stats.total], ['待复习', stats.due_now], ['已掌握', stats.graduated],
            ['保持率', Math.round((stats.avg_retention || 0) * 100) + '%']].map(([l, v]) => (
            <View key={l} style={s.kpi}><Text style={s.kpiV}>{v}</Text><Text style={s.muted}>{l}</Text></View>
          ))}
        </View>
      )}

      <View style={s.card}>
        <View style={s.row}>
          <Text style={s.h3}>↻ 今日复习队列</Text>
          <TouchableOpacity onPress={load}><Text style={{ color: colors.accent }}>⟳ 刷新</Text></TouchableOpacity>
        </View>
        {!!msg && <Text style={s.muted}>{msg}</Text>}
        {queue.map((it) => (
          <View key={it.problem_id} style={s.item}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '600' }}>{it.problem_id} <Text style={s.tag}>{STATUS[it.status]}</Text></Text>
              <Text style={s.muted}>保持率 {Math.round(it.retention * 100)}% · 间隔 {it.interval_days} 天</Text>
            </View>
            <TouchableOpacity style={[s.gbtn, { backgroundColor: colors.good }]} onPress={() => grade(it.problem_id, true)}>
              <Text style={s.gtxt}>答对</Text></TouchableOpacity>
            <TouchableOpacity style={[s.gbtn, { backgroundColor: colors.bad }]} onPress={() => grade(it.problem_id, false)}>
              <Text style={s.gtxt}>答错</Text></TouchableOpacity>
          </View>
        ))}
      </View>
      <Text style={s.note}>排程：SM-2 间隔重复 + 艾宾浩斯遗忘曲线。答对则间隔拉长，答错则重学。</Text>
    </ScrollView>
  )
}

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.bg },
  card: { backgroundColor: colors.panel, borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: colors.line },
  kpis: { flexDirection: 'row', gap: 10, marginBottom: 12 },
  kpi: { flex: 1, backgroundColor: colors.panel, borderRadius: 12, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: colors.line },
  kpiV: { fontSize: 20, fontWeight: '700', color: colors.accent },
  h3: { fontWeight: '700', fontSize: 15 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  muted: { color: colors.muted, fontSize: 12, marginTop: 4 },
  note: { color: colors.muted, fontSize: 11, fontStyle: 'italic', paddingHorizontal: 4 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.line },
  tag: { fontSize: 11, color: colors.warn },
  gbtn: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8 },
  gtxt: { color: '#fff', fontWeight: '700', fontSize: 13 },
})
