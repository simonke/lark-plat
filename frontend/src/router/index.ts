import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', redirect: '/login' },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem('lark_token')
  if (!token && to.name !== 'login') {
    return { name: 'login' }
  }
  return true
})

export default router
