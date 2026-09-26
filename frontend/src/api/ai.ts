/**
 * AIOps API (P4) — frontend/src/api/ai.ts
 * Contract: @架构 P4 tuple v1 (seq3203/seq3207/seq3212) + backend/services/ai_service.py (ff0fc80).
 * Gates are feature-first then perm (`ai:use`; `/ai/actions` needs `ai:admin`); a disabled
 * feature flag surfaces as HTTP 400, so callers should render an "未启用" empty state on error.
 * AI output is non-authoritative: never expose a bypass-approval write entry from here.
 */
import http from './http'
import type {
  Result,
  Page,
  OpsEvent,
  OpsEventQuery,
  AiAction,
  AiActionQuery,
  TicketSuggestion,
  TicketSimilarResult,
  SemanticSearchIn,
  SemanticSearchResult,
  KbAnswerIn,
  KbAnswerResult,
  AiFeedbackIn,
  AlertAggregateQuery,
  AlertAggregateResult,
  RcaReport,
  PlaybookSuggestIn,
  PlaybookSuggestion,
} from './types'

// ---------------------------------------------------------------- E1 ops events

export async function listEvents(params?: OpsEventQuery): Promise<Page<OpsEvent>> {
  const { data } = await http.get<Result<Page<OpsEvent>>>('/events', { params })
  return data.data
}

export async function getEvent(id: number): Promise<OpsEvent> {
  const { data } = await http.get<Result<OpsEvent>>(`/events/${id}`)
  return data.data
}

// ---------------------------------------------------------------- E2 ticket assist

export async function ticketSuggest(ticketId: number, context?: string): Promise<TicketSuggestion> {
  const body = context ? { context } : {}
  const { data } = await http.post<Result<TicketSuggestion>>(`/tickets/${ticketId}/ai/suggest`, body)
  return data.data
}

export async function ticketSimilar(ticketId: number, limit = 5): Promise<TicketSimilarResult> {
  const { data } = await http.get<Result<TicketSimilarResult>>(`/tickets/${ticketId}/ai/similar`, {
    params: { limit },
  })
  return data.data
}

// ---------------------------------------------------------------- E3 kb RAG

export async function kbSearchSemantic(payload: SemanticSearchIn): Promise<SemanticSearchResult> {
  const { data } = await http.post<Result<SemanticSearchResult>>('/kb/search/semantic', payload)
  return data.data
}

export async function kbAnswer(payload: KbAnswerIn): Promise<KbAnswerResult> {
  const { data } = await http.post<Result<KbAnswerResult>>('/kb/ai/answer', payload)
  return data.data
}

// ---------------------------------------------------------------- E7/E8 governance

export async function aiFeedback(payload: AiFeedbackIn): Promise<AiAction> {
  const { data } = await http.post<Result<AiAction>>('/ai/feedback', payload)
  return data.data
}

export async function listAiActions(params?: AiActionQuery): Promise<Page<AiAction>> {
  const { data } = await http.get<Result<Page<AiAction>>>('/ai/actions', { params })
  return data.data
}

// ---------------------------------------------------------------- P5 E4 alert aggregation / RCA

/** E4: read-time alert aggregation (flag `ai.rca` + perm `ai:use`; off -> 400). */
export async function aggregateAlerts(params?: AlertAggregateQuery): Promise<AlertAggregateResult> {
  const { data } = await http.get<Result<AlertAggregateResult>>('/monitor/alerts/aggregate', { params })
  return data.data
}

/** E4: root-cause candidates for one alert (depth 0..3, default 2; `<0`/`>3` -> 422). */
export async function alertRca(alertId: number, depth?: number): Promise<RcaReport> {
  const body = depth === undefined ? {} : { depth }
  const { data } = await http.post<Result<RcaReport>>(`/monitor/alerts/${alertId}/ai/rca`, body)
  return data.data
}

// ---------------------------------------------------------------- P5 E5 playbook suggestion

/** E5: advisory playbook draft (flag `ai.playbook` + perm `ai:use`; adoption reuses /workflows). */
export async function suggestPlaybook(payload: PlaybookSuggestIn): Promise<PlaybookSuggestion> {
  const { data } = await http.post<Result<PlaybookSuggestion>>('/workflows/ai/suggest', payload)
  return data.data
}
