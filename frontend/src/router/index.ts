import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import { hasToken } from '../api/tokens'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('../views/DashboardView.vue'),
      },
      {
        path: 'system/users',
        name: 'system-users',
        component: () => import('../views/users/UsersView.vue'),
      },
      {
        path: 'system/roles',
        name: 'system-roles',
        component: () => import('../views/roles/RolesView.vue'),
      },
      {
        path: 'system/audit-logs',
        name: 'system-audit-logs',
        component: () => import('../views/audit/AuditLogsView.vue'),
      },
      {
        path: 'assets/hosts',
        name: 'assets-hosts',
        component: () => import('../views/assets/HostsView.vue'),
      },
      {
        path: 'assets/hosts/:id',
        name: 'assets-host-detail',
        component: () => import('../views/assets/HostDetailView.vue'),
      },
      {
        path: 'assets/groups',
        name: 'assets-groups',
        component: () => import('../views/assets/GroupsView.vue'),
      },
      {
        path: 'assets/credentials',
        name: 'assets-credentials',
        component: () => import('../views/assets/CredentialsView.vue'),
      },
      {
        path: 'scripts',
        name: 'scripts',
        component: () => import('../views/scripts/ScriptsView.vue'),
      },
      {
        path: 'exec/tasks',
        name: 'exec-tasks',
        component: () => import('../views/exec/ExecTasksView.vue'),
      },
      {
        path: 'operations/approvals',
        name: 'operations-approvals',
        component: () => import('../views/approval/ApprovalView.vue'),
      },
      {
        path: 'operations/terminals',
        name: 'operations-terminals',
        component: () => import('../views/terminal/TerminalView.vue'),
      },
      {
        path: 'operations/notifications',
        name: 'operations-notifications',
        component: () => import('../views/notify/NotifyView.vue'),
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (!hasToken() && to.name !== 'login') {
    return { name: 'login' }
  }
  if (hasToken() && to.name === 'login') {
    return { path: '/' }
  }
  return true
})

export default router
