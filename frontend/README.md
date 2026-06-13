# 智考通 · 前端

两套前端，对接同一 FastAPI 后端（`backend/`，已开启 CORS）：

| 端 | 技术 | 目录 | 面向 |
|---|---|---|---|
| 管理后台 | **Vue3 + Vite** | [`admin-vue/`](admin-vue) | 教师/运营：学情诊断、变式题审核、错题复习、模型监控/灰度/漂移 |
| 学生端 | **React Native（Expo）** | [`student-rn/`](student-rn) | 学生：诊断雷达、苏格拉底解题、自适应推荐、错题复习 |

## 先启动后端

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 管理后台（Vue3，浏览器可跑）

```bash
cd frontend/admin-vue
npm install
npm run dev          # → http://localhost:5173  （Vite 已把 /api 代理到 :8000）
```
页面：
- **概览**：学科/知识图谱、模型监控告警、A/B 灰度、PSI 漂移。
- **学情诊断**：输入学生 ID（或「生成示例数据并诊断」）→ 跨学科能力雷达 + 薄弱点 + 错误/能力画像 + ZPD 推荐。
- **提分规划**：每日时长 → 提分性价比排序 + 倒计时每日计划（含熔断日）+ **模考估分**；可**录入真实模考成绩**，自动校准估分 + 识别「会做却失分」+ 重排各科优先级；还可**按题型录入得分**（选择/填空/解答·易中难压轴）→ 定位"丢在哪类题" → **限时训练**（选择手滑/压轴抢分）自动排进每天首项。
- **变式题审核**：生成参数化变式（符号求解保证正确）→ 质检报告 → 教师通过/驳回。
- **错题复习**：到期队列（遗忘紧迫度排序）+ 统计 + 7 天预测。

> 已在本机以 Vite+Vue3 构建并联调通过；雷达图为手写 SVG，无图表库依赖。

## 学生端（React Native / Expo）

```bash
cd frontend/student-rn
npm install
npx expo start        # 扫码用 Expo Go 打开，或按 w 开网页版
```
- **真机/模拟器访问开发机**：改 `app.json` 的 `extra.apiBase`——Android 模拟器用 `http://10.0.2.2:8000/api/v1`，真机用电脑局域网 IP，Expo Web 用 `127.0.0.1`。
- 五个底部 Tab：诊断（雷达）/ **AI 提分规划**（性价比排序 + 倒计时计划）/ 苏格拉底解题（**三级门控，绝不直接给答案**）/ 今日推荐 / 错题本（SM-2 复习）。

## 生产部署
- 管理后台 `npm run build` → 静态资源由 Nginx/CDN 托管，`/api` 反代到后端。
- 学生端 `eas build` 出 iOS/Android 包；`extra.apiBase` 指向生产网关。
