import Constants from 'expo-constants'

// 真机/模拟器访问开发机：Android 模拟器用 10.0.2.2，真机用电脑 LAN IP。
// 在 app.json 的 extra.apiBase 配置；Expo Web 用 127.0.0.1 即可。
const BASE = Constants.expoConfig?.extra?.apiBase || 'http://127.0.0.1:8000/api/v1'

async function req(method, path, body) {
  const opt = { method, headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined) opt.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opt)
  const text = await res.text()
  let data
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const d = data && data.detail ? data.detail : data
    const err = new Error(typeof d === 'string' ? d : (d?.reason || res.statusText))
    err.status = res.status; err.detail = d
    throw err
  }
  return data
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),
  answer: (b) => api.post('/answer', b),
  diagnosis: (uid, subject = '') => api.get(`/diagnosis/${uid}${subject ? `?subject=${subject}` : ''}`),
  recommend: (uid, subject = '', n = 8) => api.get(`/recommend/${uid}?n=${n}${subject ? `&subject=${subject}` : ''}`),
  plan: (b) => api.post('/plan', b),
  score: (uid) => api.get(`/score/${uid}`),
  submitMock: (b) => api.post('/mock', b),
  examPaper: (subject = '') => api.get(`/exam/paper${subject ? `?subject=${subject}` : ''}`),
  execution: (uid) => api.get(`/execution/${uid}`),
  solve: (b) => api.post('/solve', b),
  reviewQueue: (uid) => api.get(`/review/queue/${uid}`),
  reviewStats: (uid) => api.get(`/review/stats/${uid}`),
  reviewGrade: (b) => api.post('/review/grade', b),
}

export const USER = 'rn_student'
