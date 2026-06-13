import React, { useState } from 'react'
import { View, Text, ScrollView, TextInput, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native'
import { api, USER } from '../api'
import { colors, SUBJECT_CN } from '../theme'

const TIER = { 易: colors.good, 中: colors.warn, 难: colors.bad }
const SUBS = [['math', '数学'], ['physics', '物理'], ['chemistry', '化学'], ['biology', '生物']]

export default function PlanScreen() {
  const [plan, setPlan] = useState(null)
  const [exec, setExec] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('先在「诊断」页生成作答，再来生成提分计划')
  const [mock, setMock] = useState({ math: '', physics: '', chemistry: '', biology: '' })
  const [mockMsg, setMockMsg] = useState('')
  const [showSec, setShowSec] = useState(false)
  const [secSubject, setSecSubject] = useState('math')
  const [paper, setPaper] = useState({})
  const [secInput, setSecInput] = useState({})

  const run = async () => {
    setBusy(true); setMsg('')
    try {
      const [p, ex] = await Promise.all([
        api.plan({ user_id: USER, daily_minutes: 120 }),
        api.execution(USER).catch(() => null),
      ])
      setPlan(p)
      setExec(ex && ex.has_section_data ? ex : null)
    } catch (e) { setMsg('失败：' + e.message) } finally { setBusy(false) }
  }
  const sumLoss = (k) => (exec?.subjects || []).reduce((a, s) => a + (s[k] || 0), 0).toFixed(1)

  const toggleSec = async () => {
    const next = !showSec; setShowSec(next)
    if (next && !Object.keys(paper).length) { try { setPaper(await api.examPaper()) } catch {} }
  }
  const setSec = (subj, sid, val) =>
    setSecInput((p) => ({ ...p, [subj]: { ...(p[subj] || {}), [sid]: val } }))

  const submitMock = async () => {
    const scores = {}
    for (const [k] of SUBS) if (mock[k] !== '') scores[k] = Number(mock[k])
    if (!Object.keys(scores).length) { setMockMsg('请至少填一科分数'); return }
    const section_scores = {}
    for (const [subj, secs] of Object.entries(secInput)) {
      const got = {}
      for (const [sid, v] of Object.entries(secs)) if (v !== '' && v != null) got[sid] = Number(v)
      if (Object.keys(got).length) section_scores[subj] = got
    }
    setMockMsg('提交并重排中…')
    try {
      const body = { user_id: USER, exam_name: '模考', scores }
      if (Object.keys(section_scores).length) body.section_scores = section_scores
      await api.submitMock(body); await run()
      setMockMsg(Object.keys(section_scores).length
        ? '✓ 已定位应试丢分，限时训练已排进每日计划' : '✓ 计划已按真实模考反馈更新')
    } catch (e) { setMockMsg('失败：' + e.message) }
  }

  return (
    <ScrollView style={s.page} contentContainerStyle={{ padding: 14 }}>
      <View style={s.card}>
        <TouchableOpacity style={s.btn} onPress={run} disabled={busy}>
          <Text style={s.btnTxt}>{busy ? '规划中…' : '生成我的提分计划'}</Text>
        </TouchableOpacity>
        {busy && <ActivityIndicator style={{ marginTop: 10 }} color={colors.accent} />}
        {!!msg && <Text style={s.muted}>{msg}</Text>}
      </View>

      {plan && (
        <>
          <View style={s.kpis}>
            <View style={s.kpi}><Text style={[s.kpiV, { color: colors.bad }]}>{plan.days_left}</Text><Text style={s.muted}>距高考(天)</Text></View>
            <View style={s.kpi}><Text style={s.kpiV}>{Math.round(plan.total_study_minutes / 60)}h</Text><Text style={s.muted}>总投入</Text></View>
            <View style={s.kpi}><Text style={[s.kpiV, { color: colors.good }]}>+{plan.expected_score_gain}</Text><Text style={s.muted}>预计提分</Text></View>
          </View>
          <View style={[s.card, { backgroundColor: colors.accentSoft }]}>
            <Text style={s.h3}>🎯 模考估分 {plan.mock_calibrated ? '· 已校准' : '· 待校准'}</Text>
            <Text style={{ fontSize: 22, fontWeight: '700', color: colors.accent }}>
              {plan.projected_score_now}<Text style={s.muted}> / {plan.projected_full} 分</Text></Text>
            {!!plan.feedback_note && <Text style={{ color: colors.accent, fontSize: 13, marginTop: 6 }}>↳ {plan.feedback_note}</Text>}
            <Text style={[s.muted, { marginTop: 4 }]}>{plan.projected_note}</Text>
          </View>

          <View style={s.card}>
            <Text style={s.h3}>📥 录入真实模考（作为反馈信号）</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
              {SUBS.map(([k, cn]) => (
                <View key={k} style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Text style={s.muted}>{cn}</Text>
                  <TextInput style={s.mInput} keyboardType="numeric" value={mock[k]}
                    onChangeText={(t) => setMock({ ...mock, [k]: t })} placeholder="—" />
                </View>
              ))}
              <TouchableOpacity style={[s.btn, { paddingVertical: 8, paddingHorizontal: 12 }]} onPress={submitMock}>
                <Text style={s.btnTxt}>提交并重排</Text></TouchableOpacity>
            </View>
            <TouchableOpacity onPress={toggleSec} style={{ marginTop: 10 }}>
              <Text style={{ color: colors.accent, fontSize: 13 }}>
                {showSec ? '▾' : '▸'} ✏️ 按题型录入（定位选择/压轴丢分 → 开限时训练）</Text>
            </TouchableOpacity>
            {showSec && (
              <View style={{ marginTop: 8 }}>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
                  {SUBS.map(([k, cn]) => (
                    <TouchableOpacity key={k} onPress={() => setSecSubject(k)}
                      style={[s.chip, secSubject === k && s.chipOn]}>
                      <Text style={[s.chipTxt, secSubject === k && { color: '#fff' }]}>{cn}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {(paper[secSubject] || []).map((sec) => (
                    <View key={sec.id} style={{ flexDirection: 'row', alignItems: 'center' }}>
                      <Text style={s.muted}>{sec.name}/{sec.points}</Text>
                      <TextInput style={s.mInput} keyboardType="numeric" placeholder="—"
                        value={(secInput[secSubject] || {})[sec.id] ?? ''}
                        onChangeText={(t) => setSec(secSubject, sec.id, t)} />
                    </View>
                  ))}
                </View>
              </View>
            )}
            {!!mockMsg && <Text style={s.muted}>{mockMsg}</Text>}
            <Text style={[s.muted, { fontStyle: 'italic' }]}>模型会识别「会做却失分」、校准估分、把时间投向考场最该补的科目。</Text>
          </View>

          {!!exec && (
            <View style={[s.card, { backgroundColor: '#fffbeb', borderColor: '#fde68a' }]}>
              <Text style={s.h3}>🔍 题型级丢分归因（该拿多少 vs 实得）</Text>
              <View style={{ flexDirection: 'row', gap: 18, marginBottom: 8 }}>
                <Text><Text style={{ fontSize: 20, fontWeight: '700', color: colors.bad }}>{sumLoss('total_loss')}</Text>
                  <Text style={s.muted}> 分 总丢分</Text></Text>
                <Text><Text style={{ fontSize: 20, fontWeight: '700', color: colors.good }}>{sumLoss('fixable_loss')}</Text>
                  <Text style={s.muted}> 分 会做却丢</Text></Text>
              </View>
              {exec.subjects.map((se) => (
                <View key={se.subject} style={{ marginBottom: 8 }}>
                  <Text style={{ fontWeight: '700', fontSize: 13 }}>{SUBJECT_CN[se.subject] || se.subject}
                    <Text style={s.muted}>  丢{se.total_loss} · 可挽回{se.fixable_loss}</Text></Text>
                  {se.sections.filter((x) => x.loss > 0).map((x) => (
                    <View key={x.section_id} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2 }}>
                      <Text style={{ fontSize: 12, flex: 1 }}>{x.name}
                        <Text style={[s.tier, { color: TIER[x.tier] || colors.bad }]}> {x.tier}</Text></Text>
                      <Text style={s.muted}>应得{x.expected}/实得{x.got == null ? '—' : x.got}</Text>
                      <Text style={{ fontSize: 12, color: colors.bad, fontWeight: '700', width: 54, textAlign: 'right' }}>丢{x.loss}</Text>
                    </View>
                  ))}
                </View>
              ))}
              <Text style={[s.muted, { fontStyle: 'italic' }]}>「应得」=按你掌握度这类题正常该拿的分；丢分即「会做却没拿到」，下方限时训练照此开方。</Text>
            </View>
          )}

          {!!(plan.timed_drills && plan.timed_drills.length) && (
            <View style={[s.card, { backgroundColor: '#fff7ed', borderColor: '#fed7aa' }]}>
              <Text style={s.h3}>⏱ 应试丢分 → 限时训练（按可挽回分，已排进每日首项）</Text>
              {plan.timed_drills.map((d, i) => (
                <View key={i} style={s.prow}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: '600' }}>{d.title}
                      <Text style={[s.tier, { color: TIER[d.tier] || colors.bad }]}> {d.tier}</Text></Text>
                    <Text style={s.muted}>{d.n_problems}题/{d.time_limit_min}min · {d.goal} · 针对{d.cause}</Text>
                  </View>
                  <Text style={s.gain}>+{d.recoverable_points}</Text>
                </View>
              ))}
            </View>
          )}

          <View style={s.card}>
            <Text style={s.h3}>① 先补这些（分/小时最高）</Text>
            {plan.priorities.slice(0, 8).map((it) => (
              <View key={it.concept_id} style={s.prow}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: '600' }}>{it.concept_name}
                    <Text style={s.tag}> {SUBJECT_CN[it.subject]}</Text>
                    <Text style={[s.tier, { color: TIER[it.learnability] }]}> {it.learnability}</Text></Text>
                  <Text style={s.muted}>高考{it.exam_weight}分 · 掌握{Math.round(it.mastery * 100)}% · {it.allocated_minutes}min</Text>
                </View>
                <Text style={s.gain}>+{it.expected_gain}</Text>
              </View>
            ))}
          </View>

          <View style={s.card}>
            <Text style={s.h3}>② 每日计划（跨学科交错 + 错题复习）</Text>
            {plan.days.map((d) => (
              <View key={d.day_index} style={[s.day, d.is_blackout && { backgroundColor: '#fef2f2', borderColor: '#fecaca' }]}>
                <Text style={{ fontWeight: '700', marginBottom: 4 }}>
                  第{d.day_index + 1}天 · {d.date.slice(5)} <Text style={s.muted}>{d.total_minutes}min{d.is_blackout ? ' 🔒熔断' : ''}</Text>
                </Text>
                {d.tasks.map((t, i) => (
                  <Text key={i} style={[s.task, t.kind === 'timed_drill' && { color: '#c2410c', fontWeight: '600' }]}>
                    {t.kind === 'timed_drill'
                      ? `⏱ ${t.concept_name}  ${t.minutes}min/${t.n_problems}题`
                      : t.kind === 'learn'
                        ? `📘 ${SUBJECT_CN[t.subject] || t.subject}·${t.concept_name}  ${t.minutes}min/${t.n_problems}题`
                        : `↻ 错题复习 ${t.minutes}min`}
                  </Text>
                ))}
              </View>
            ))}
          </View>
        </>
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.bg },
  card: { backgroundColor: colors.panel, borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: colors.line },
  h3: { fontWeight: '700', marginBottom: 10, fontSize: 15 },
  btn: { backgroundColor: colors.accent, borderRadius: 10, padding: 13, alignItems: 'center' },
  btnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  muted: { color: colors.muted, fontSize: 12, marginTop: 3 },
  mInput: { borderWidth: 1, borderColor: colors.line, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, width: 56, marginLeft: 4, fontSize: 14 },
  kpis: { flexDirection: 'row', gap: 10, marginBottom: 12 },
  kpi: { flex: 1, backgroundColor: colors.panel, borderRadius: 12, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: colors.line },
  kpiV: { fontSize: 22, fontWeight: '700', color: colors.accent },
  prow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.line },
  tag: { fontSize: 11, color: colors.accent },
  tier: { fontSize: 11, fontWeight: '700' },
  chip: { borderWidth: 1, borderColor: colors.line, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 4 },
  chipOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipTxt: { fontSize: 12, color: colors.ink },
  gain: { color: colors.good, fontWeight: '700', fontSize: 15 },
  day: { borderWidth: 1, borderColor: colors.line, borderRadius: 10, padding: 10, marginBottom: 8, backgroundColor: '#fafbff' },
  task: { fontSize: 12, color: colors.ink, lineHeight: 19 },
})
