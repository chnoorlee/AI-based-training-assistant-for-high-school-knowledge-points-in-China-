import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: '概览', component: () => import('./views/Dashboard.vue') },
  { path: '/diagnosis', name: '学情诊断', component: () => import('./views/Diagnosis.vue') },
  { path: '/plan', name: '提分规划', component: () => import('./views/Plan.vue') },
  { path: '/variant', name: '变式题审核', component: () => import('./views/VariantReview.vue') },
  { path: '/review', name: '错题复习', component: () => import('./views/ReviewBook.vue') },
]

export default createRouter({ history: createWebHashHistory(), routes })
