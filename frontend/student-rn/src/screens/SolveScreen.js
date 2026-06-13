import React, { useState } from 'react'
import { View, Text, ScrollView, TextInput, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native'
import { api, USER } from '../api'
import { colors } from '../theme'

const NEXT = { '-1': '获取苏格拉底引导', 0: '下一步：分步思路', 1: '查看完整解析', 2: '✓ 已完整（改题号可重练）' }

export default function SolveScreen() {
  const [pid, setPid] = useState('M0002')
  const [resp, setResp] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const level = resp ? resp.reveal_level : -1

  const next = async () => {
    if (level >= 2) return
    setBusy(true); setErr('')
    try {
      setResp(await api.solve({ user_id: USER, problem_id: pid.trim(), reveal_level: 2 }))
    } catch (e) {
      setErr(e.status === 403 ? '已熔断：' + (e.detail?.reason || '高考期间停用') : '失败：' + e.message)
    } finally { setBusy(false) }
  }

  return (
    <ScrollView style={s.page} contentContainerStyle={{ padding: 14 }}>
      <View style={s.card}>
        <Text style={s.muted}>题号（如 M0002 数学 / P0003 物理 / B0001 生物）</Text>
        <TextInput style={s.input} value={pid}
          onChangeText={(t) => { setPid(t); setResp(null); setErr('') }} autoCapitalize="characters" />
        <TouchableOpacity style={[s.btn, level >= 2 && s.btnDone]} onPress={next} disabled={busy || level >= 2}>
          <Text style={s.btnTxt}>{NEXT[level]}</Text>
        </TouchableOpacity>
        {busy && <ActivityIndicator style={{ marginTop: 10 }} color={colors.accent} />}
        {!!err && <Text style={[s.muted, { color: colors.bad }]}>{err}</Text>}
        <Text style={s.note}>原则：绝不上传即给答案——先引导思考，再逐级展开。</Text>
      </View>

      {resp && (
        <>
          {/* HINT：苏格拉底引导问题 */}
          <View style={s.card}>
            <Text style={s.h3}>① 苏格拉底引导</Text>
            {resp.socratic_questions.map((q, i) => (
              <Text key={i} style={s.qline}>{i + 1}. {q}</Text>
            ))}
          </View>

          {/* GUIDED：分步思路 */}
          {level >= 1 && (
            <View style={s.card}>
              <Text style={s.h3}>② 分步思路{level < 2 ? '（暂不含最终答案）' : ''}</Text>
              {resp.guided_steps.map((st, i) => <Text key={i} style={s.step}>· {st}</Text>)}
            </View>
          )}

          {/* FULL：完整解析 + 答案 */}
          {level >= 2 && (
            <View style={s.card}>
              <Text style={s.h3}>③ 完整思维链与答案</Text>
              {resp.chain_of_thought.map((st, i) => <Text key={i} style={s.step}>· {st}</Text>)}
              {resp.final_answer
                ? <View style={s.answer}><Text style={s.answerTxt}>✅ 答案：{resp.final_answer}</Text></View>
                : <Text style={s.muted}>（自由输入题暂无标准答案库）</Text>}
              <Text style={s.muted}>幻觉校验：{resp.fact_check.passed ? '通过 ✓' : '待人工复核'}
                {resp.fact_check.verified_concepts?.length ? ' · 已核验 ' + resp.fact_check.verified_concepts.join('、') : ''}</Text>
            </View>
          )}

          <Text style={[s.muted, { paddingHorizontal: 4 }]}>{resp.notice}</Text>
        </>
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.bg },
  card: { backgroundColor: colors.panel, borderRadius: 14, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: colors.line },
  h3: { fontWeight: '700', marginBottom: 10, fontSize: 15 },
  input: { borderWidth: 1, borderColor: colors.line, borderRadius: 10, padding: 11, marginTop: 6, marginBottom: 10, fontSize: 15 },
  btn: { backgroundColor: colors.accent, borderRadius: 10, padding: 13, alignItems: 'center' },
  btnDone: { backgroundColor: colors.good },
  btnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  muted: { color: colors.muted, fontSize: 12, marginTop: 8 },
  note: { color: colors.muted, fontSize: 11, marginTop: 10, fontStyle: 'italic' },
  qline: { lineHeight: 23, marginBottom: 6, color: colors.ink },
  step: { lineHeight: 22, marginBottom: 4, color: colors.ink },
  answer: { backgroundColor: '#dcfce7', borderRadius: 10, padding: 12, marginTop: 8 },
  answerTxt: { color: '#166534', fontWeight: '700', lineHeight: 22 },
})
