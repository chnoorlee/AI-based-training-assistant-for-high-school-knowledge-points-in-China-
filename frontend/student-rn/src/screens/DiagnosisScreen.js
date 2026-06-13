import React, { useState } from 'react'
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native'
import Radar from '../components/Radar'
import { api, USER } from '../api'
import { colors } from '../theme'

const SAMPLE = [
  ['M0001', true], ['M0002', false], ['M0003', false], ['M0006', true],
  ['P0001', false], ['P0002', true], ['C0001', true], ['C0004', false],
  ['B0001', false], ['B0003', true],
]
const LVL = { unmastered: '未掌握', initial: '初步掌握', basic: '基本掌握', proficient: '熟练掌握' }

export default function DiagnosisScreen() {
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('点下方按钮，生成示例作答并诊断')

  const weak = () => {
    if (!report) return []
    const m = Object.fromEntries(report.concept_mastery.map((c) => [c.concept_id, c]))
    return report.weak_concepts.map((id) => m[id]).filter(Boolean).slice(0, 6)
  }

  const run = async () => {
    setBusy(true); setMsg('正在写入作答并诊断…')
    try {
      for (const [pid, ok] of SAMPLE)
        await api.answer({ user_id: USER, problem_id: pid, correct: ok, time_spent_s: ok ? 45 : 110 })
      setReport(await api.diagnosis(USER))
      setMsg('')
    } catch (e) { setMsg('失败：' + e.message) } finally { setBusy(false) }
  }

  return (
    <ScrollView style={s.page} contentContainerStyle={{ padding: 14 }}>
      <View style={s.card}>
        <TouchableOpacity style={s.btn} onPress={run} disabled={busy}>
          <Text style={s.btnTxt}>{busy ? '诊断中…' : '生成示例作答并诊断'}</Text>
        </TouchableOpacity>
        {busy && <ActivityIndicator style={{ marginTop: 10 }} color={colors.accent} />}
        {!!msg && <Text style={s.muted}>{msg}</Text>}
      </View>

      {report && (
        <>
          <View style={s.card}>
            <Text style={s.h3}>🧭 能力雷达图（跨学科综合）</Text>
            <View style={{ alignItems: 'center' }}>
              <Radar axes={report.radar.map((r) => ({ label: r.module, value: r.score }))} size={300} />
            </View>
            <Text style={s.overall}>整体掌握度 {Math.round(report.overall_mastery * 100)}%
              <Text style={s.muted}>  · {report.n_responses} 条作答</Text></Text>
          </View>

          <View style={s.card}>
            <Text style={s.h3}>⚠️ 优先突破的薄弱点</Text>
            {weak().map((c) => (
              <View key={c.concept_id} style={{ marginBottom: 11 }}>
                <View style={s.row}>
                  <Text style={{ flex: 1 }}>{c.concept_name}</Text>
                  <Text style={s.muted}>{LVL[c.level]} · 预测答对 {Math.round(c.predicted_correct_prob * 100)}%</Text>
                </View>
                <View style={s.track}>
                  <View style={[s.fill, { width: `${c.score * 100}%`, backgroundColor: c.score < 0.4 ? colors.bad : colors.warn }]} />
                </View>
              </View>
            ))}
          </View>

          <View style={s.card}>
            <Text style={s.h3}>📝 诊断解读</Text>
            <Text style={{ lineHeight: 22, color: colors.ink }}>{report.explanation}</Text>
          </View>
        </>
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.bg },
  card: { backgroundColor: colors.panel, borderRadius: 14, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: colors.line },
  h3: { fontWeight: '700', marginBottom: 12, fontSize: 15 },
  btn: { backgroundColor: colors.accent, borderRadius: 10, padding: 13, alignItems: 'center' },
  btnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  muted: { color: colors.muted, fontSize: 12, marginTop: 8 },
  overall: { textAlign: 'center', marginTop: 6, fontSize: 17, fontWeight: '700', color: colors.accent },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  track: { backgroundColor: '#eef2f7', height: 8, borderRadius: 6, marginTop: 4, overflow: 'hidden' },
  fill: { height: 8, borderRadius: 6 },
})
