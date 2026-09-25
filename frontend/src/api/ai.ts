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
