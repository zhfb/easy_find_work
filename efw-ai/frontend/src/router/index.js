import { createRouter, createWebHistory } from 'vue-router'
const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
  { path: '/applications', name: 'applications', component: () => import('../views/ApplicationsView.vue') },
  { path: '/semi-queue', name: 'semiQueue', component: () => import('../views/SemiQueueView.vue') },
  { path: '/tasks/:id', name: 'taskDetail', component: () => import('../views/TaskDetailView.vue') },
  { path: '/config', name: 'config', component: () => import('../views/ConfigView.vue') },
  { path: '/chat', name: 'chat', component: () => import('../views/ChatView.vue') },
]
export default createRouter({ history: createWebHistory(), routes })
