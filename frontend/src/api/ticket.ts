/**
 * Ticket API (P3-1) — frontend/src/api/ticket.ts
 * Contract: api-design-v3.md §5 (14 endpoints). Shapes @ backend/app/schemas/ticket.py.
 * All writes go through the existing permission guards; the service gates on
 * `feature.ticket` (default False -> HTTP 400 "feature disabled").
 */
import http from './http'
import type {
  Page,
  Result,
  TicketOut,
  TicketDetail,
  TicketQuery,
  TicketCreate,
  TicketUpdate,
  TicketAssignIn,
  TicketDoneIn,
  TicketCommentOut,
  TicketAttachmentOut,
  TicketRefIn,
} from './types'

export async function listTickets(params?: TicketQuery): Promise<Page<TicketOut>> {
  const { data } = await http.get<Result<Page<TicketOut>>>('/tickets', { params })
  return data.data
}

export async function getTicket(id: number): Promise<TicketDetail> {
  const { data } = await http.get<Result<TicketDetail>>(`/tickets/${id}`)
  return data.data
}

export async function createTicket(payload: TicketCreate): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>('/tickets', payload)
  return data.data
}

export async function updateTicket(id: number, payload: TicketUpdate): Promise<TicketOut> {
  const { data } = await http.put<Result<TicketOut>>(`/tickets/${id}`, payload)
  return data.data
}

export async function assignTicket(id: number, payload: TicketAssignIn): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>(`/tickets/${id}/assign`, payload)
  return data.data
}

export async function acceptTicket(id: number): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>(`/tickets/${id}/accept`)
  return data.data
}

export async function processTicket(id: number): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>(`/tickets/${id}/process`)
  return data.data
}

export async function doneTicket(id: number, payload: TicketDoneIn): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>(`/tickets/${id}/done`, payload)
  return data.data
}

export async function closeTicket(id: number): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>(`/tickets/${id}/close`)
  return data.data
}

export async function reopenTicket(id: number): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>(`/tickets/${id}/reopen`)
  return data.data
}

export async function cancelTicket(id: number): Promise<TicketOut> {
  const { data } = await http.post<Result<TicketOut>>(`/tickets/${id}/cancel`)
  return data.data
}

export async function addTicketComment(id: number, content: string): Promise<TicketCommentOut> {
  const { data } = await http.post<Result<TicketCommentOut>>(`/tickets/${id}/comments`, { content })
  return data.data
}

export async function addTicketRef(id: number, payload: TicketRefIn): Promise<void> {
  await http.post<Result<unknown>>(`/tickets/${id}/refs`, payload)
}

export async function uploadTicketAttachments(
  id: number,
  files: File[],
): Promise<TicketAttachmentOut[]> {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  const { data } = await http.post<Result<{ ticket_id: number; attachments: TicketAttachmentOut[] }>>(
    `/tickets/${id}/attachments`,
    form,
  )
  return data.data.attachments
}
