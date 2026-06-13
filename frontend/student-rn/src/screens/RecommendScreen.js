import React, { useState } from 'react'
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native'
import { api, USER } from '../api'
import { colors } from '../theme'

const REASON = {
  weakness: { t: '强化', c: '#fee2e2', tc: '#991b1b' },
  consolidate: { t: '巩固', c: '#fef3c7', tc: '#92400e' },
  stretch: { t: '提高', c: '#dcfce7', tc: '#166534' },
}

export default function RecommendScreen() {
  const [items, setItems] = useState(null)
  const [mix, setMix] = useState({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('点下方加载为你定制的练习（先在「诊断」页生成作答）')

  const load = async () => {
    setBusy(true); setMsg('')
    try {
      const r = await api.recommend(USER, '', 8)
      setItems(r.items); setMix(r.mix)
      if (!r.items.length) setMsg('暂无推荐，请先到「诊断」页生成作答。')
    } catch (e) { setMsg('失败：' + e.message) } finally { setBusy(false) }
  }

  return (
    <ScrollView style={s.page} contentContainerStyle={{ padding: 14 }}>
      <View style={s.card}>
        <TouchableOpacity style={s.btn} onPress={load} disabled={busy}>
          <Text style={s.btnTxt}>{busy ? '加载中…' : '加载今日推荐'}</Text>
        </TouchableOpacity>
        {busy && <ActivityIndicator style={{ marginTop: 10 }} color={colors.accent} />}
        {!!msg && <Text style={s.muted}>{msg}</Text>}
        {items && items.length > 0 && (
          <Text style={s.muted}>配比（强化/巩固/提高 = 70/20/10）：{JSON.stringify(mix)}</Text>
        )}
      </View>

      {(items || []).map((it) => {
        const r = REASON[it.reason] || { t: it.reason, c: '#eef2f7', tc: '#475569' }
        return (
          <View key={it.problem_id} style={s.card}>
            <View style={s.row}>
              <Text style={s.pid}>{it.problem_id}</Text>
              <View style={[s.pill, { backgroundColor: r.c }]}><Text style={{ color: r.tc, fontSize: 12, fontWeight: '700' }}>{r.t}</Text></View>
              <Text style={s.muted}>预测答对 {Math.round(it.predicted_correct_prob * 100)}%</Text>
            </View>
            <Text style={{ color: colors.ink, marginTop: 6, lineHeight: 20 }}>{it.rationale}</Text>
          </View>
        )
      })}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.bg },
  card: { backgroundColor: colors.panel, borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: colors.line },
  btn: { backgroundColor: colors.accent, borderRadius: 10, padding: 13, alignItems: 'center' },
  btnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  muted: { color: colors.muted, fontSize: 12, marginTop: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  pid: { fontWeight: '700', fontSize: 15 },
  pill: { paddingHorizontal: 9, paddingVertical: 2, borderRadius: 999 },
})
