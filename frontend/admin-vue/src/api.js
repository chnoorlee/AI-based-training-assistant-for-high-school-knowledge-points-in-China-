// 统一 API 封装。开发期经 Vite 代理 → FastAPI；生产用 VITE_API_BASE。
const BASE = import.meta.env.VITE_API_BASE || '/api/v1'

async function req(method, path, body) {
  const opt = { method, headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined) opt.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opt)
  const text = await res.text()
  let data
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : data
    const err = new Error(typeof detail === 'string' ? detail : (detail?.reason || res.statusText))
    err.status = res.status
    err.detail = detail
    throw err
  }
  return data
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),

  health: () => api.get('/health'),
  subjects: () => api.get('/subjects'),

  answer: (b) => api.post('/answer', b),
  diagnosis: (uid, subject = '') => api.get(`/diagnosis/${uid}${subject ? `?subject=${subject}` : ''}`),
  recommend: (uid, subject = '', n = 8) => api.get(`/recommend/${uid}?n=${n}${subject ? `&subject=${subject}` : ''}`),
  coldStart: (uid, subject = '') => api.get(`/diagnosis/cold-start?user_id=${uid}${subject ? `&subject=${subject}` : ''}`),

  plan: (b) => api.post('/plan', b),
  score: (uid) => api.get(`/score/${uid}`),
  submitMock: (b) => api.post('/mock', b),
  mockHistory: (uid) => api.get(`/mock/${uid}`),
  examPaper: (subject = '') => api.get(`/exam/paper${subject ? `?subject=${subject}` : ''}`),
  execution: (uid) => api.get(`/execution/${uid}`),

  variantGenerate: (b) => api.post('/variant/generate', b),
  variantQueue: () => api.get('/variant/review/queue'),
  variantReview: (id, b) => api.post(`/variant/review/${id}`, b),

  reviewQueue: (uid, limit = 20) => api.get(`/review/queue/${uid}?limit=${limit}`),
  reviewStats: (uid) => api.get(`/review/stats/${uid}`),
  reviewForecast: (uid) => api.get(`/review/forecast/${uid}`),
  reviewGrade: (b) => api.post('/review/grade', b),

  metrics: () => api.get('/metrics'),                 // prometheus 文本
  alerts: () => api.get('/monitoring/alerts'),
  abStatus: () => api.get('/ab/status'),
  drift: (hours = 24) => api.get(`/drift/report?hours=${hours}`),
  compliance: (uid, feature) => api.get(`/compliance?user_id=${uid}&feature=${feature}`),
}

export const SUBJECT_CN = { math: '数学', physics: '物理', chemistry: '化学', biology: '生物' }
