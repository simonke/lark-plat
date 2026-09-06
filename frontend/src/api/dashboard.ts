import http from './http'
import type { Result, DashboardStats, TrendPoint, RecentTask, RecentApproval } from './types'

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await http.get<Result<DashboardStats>>('/dashboard/stats')
  return data.data
}

export async function getTaskTrend(days = 7): Promise<TrendPoint[]> {
  const { data } = await http.get<Result<TrendPoint[]>>('/dashboard/task-trend', { params: { days } })
  return data.data
}

export async function getRecentTasks(): Promise<RecentTask[]> {
  const { data } = await http.get<Result<RecentTask[]>>('/dashboard/recent-tasks')
  return data.data
}

export async function getRecentApprovals(): Promise<RecentApproval[]> {
  const { data } = await http.get<Result<RecentApproval[]>>('/dashboard/recent-approvals')
  return data.data
}