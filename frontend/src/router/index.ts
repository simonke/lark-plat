import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'
import { hasToken } from '../api/tokens'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  {
    path: '/auth/callback',
    name: 'auth-callback',
    component: () => import('../views/AuthCallbackView.vue'),
  },
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
        path: 'system/auth-providers',
        name: 'system-auth-providers',
        component: () => import('../views/system/AuthProvidersView.vue'),
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
        path: 'assets/cmdb',
        name: 'assets-cmdb',
        component: () => import('../views/assets/RelationsView.vue'),
      },
      {
        path: 'assets/cmdb/topology',
        name: 'assets-cmdb-topology',
        component: () => import('../views/assets/CmdbTopologyView.vue'),
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
        path: 'transfer',
        name: 'transfer',
        component: () => import('../views/transfer/TransferView.vue'),
      },
      {
        path: 'schedules',
        name: 'schedules',
        component: () => import('../views/schedules/SchedulesView.vue'),
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
      {
        path: 'monitor/dashboard',
        name: 'monitor-dashboard',
        component: () => import('../views/monitoring/MonitoringDashboardView.vue'),
      },
      {
        path: 'monitor/alerts',
        name: 'monitor-alerts',
        component: () => import('../views/monitoring/AlertsView.vue'),
      },
      {
        path: 'monitor/rules',
        name: 'monitor-rules',
        component: () => import('../views/monitoring/AlertRulesView.vue'),
      },
      {
        path: 'monitor/adapters',
        name: 'monitor-adapters',
        component: () => import('../views/monitoring/AdaptersView.vue'),
      },
      {
        path: 'tickets',
        name: 'tickets',
        component: () => import('../views/ticket/TicketsView.vue'),
      },
      {
        path: 'tickets/:id',
        name: 'ticket-detail',
        component: () => import('../views/ticket/TicketDetailView.vue'),
      },
      {
        path: 'kb/articles',
        name: 'kb-articles',
        component: () => import('../views/kb/KbArticlesView.vue'),
      },
      {
        path: 'kb/articles/:id',
        name: 'kb-article',
        component: () => import('../views/kb/KbArticleView.vue'),
      },
      {
        path: 'workflows',
        name: 'workflows',
        component: () => import('../views/workflow/WorkflowsView.vue'),
      },
      {
        path: 'workflows/:id',
        name: 'workflow-detail',
        component: () => import('../views/workflow/WorkflowDetailView.vue'),
      },
      {
        path: 'workflow-runs',
        name: 'workflow-runs',
        component: () => import('../views/workflow/WorkflowRunsView.vue'),
      },
      {
        path: 'workflow-runs/:id',
        name: 'workflow-run-detail',
        component: () => import('../views/workflow/WorkflowRunDetailView.vue'),
      },
      {
        path: 'cicd/providers',
        name: 'cicd-providers',
        component: () => import('../views/cicd/ProvidersView.vue'),
      },
      {
        path: 'releases',
        name: 'releases',
        component: () => import('../views/releases/ReleasesView.vue'),
      },
      {
        path: 'releases/:id',
        name: 'release-detail',
        component: () => import('../views/releases/ReleaseDetailView.vue'),
      },
      {
        path: 'ops/incidents',
        name: 'ops-incidents',
        component: () => import('../views/ops/IncidentsView.vue'),
      },
      {
        path: 'ai/kb',
        name: 'ai-kb',
        component: () => import('../views/ai/KbAssistantView.vue'),
      },
      {
        path: 'ai/actions',
        name: 'ai-actions',
        component: () => import('../views/ai/AiActionsView.vue'),
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
  if (to.name === 'auth-callback') {
    return true
  }
  if (!hasToken() && to.name !== 'login') {
    return { name: 'login' }
  }
  if (hasToken() && to.name === 'login') {
    return { path: '/' }
  }
  return true
})

export default router
