import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listTickets,
  getTicket,
  createTicket,
  updateTicket,
  assignTicket,
  acceptTicket,
  processTicket,
  doneTicket,
  closeTicket,
  reopenTicket,
  cancelTicket,
  addTicketComment,
  addTicketRef,
  uploadTicketAttachments,
} from '../src/api/ticket'
import {
  listArticles,
  getArticle,
  createArticle,
  updateArticle,
  deleteArticle,
  listVersions,
  getVersion,
  rollbackArticle,
  listCategories,
  createCategory,
  updateCategory,
  deleteCategory,
  searchArticles,
} from '../src/api/kb'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function ok(data: unknown) {
  return { data: { code: 0, message: 'ok', data } }
}

describe('Ticket API (P3-1)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists tickets with query params', async () => {
    const page = { list: [{ id: 1, title: 't' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listTickets({
      ticket_no: 'TK-20260924-001',
      status: 'create',
      category: 'incident',
      page: 1,
      size: 10,
    })
    expect(http.get).toHaveBeenCalledWith('/tickets', {
      params: { ticket_no: 'TK-20260924-001', status: 'create', category: 'incident', page: 1, size: 10 },
    })
    expect(result).toEqual(page)
  })

  it('fetches ticket detail', async () => {
    const detail = { id: 5, refs: [], comments: [], attachments: [] }
    vi.mocked(http.get).mockResolvedValue(ok(detail))
    const result = await getTicket(5)
    expect(http.get).toHaveBeenCalledWith('/tickets/5')
    expect(result).toEqual(detail)
  })

  it('creates a ticket', async () => {
    const out = { id: 2, title: 't' }
    vi.mocked(http.post).mockResolvedValue(ok(out))
    const payload = { title: 't', category: 'incident' as const, priority: 'high' as const, description: '' }
    const result = await createTicket(payload)
    expect(http.post).toHaveBeenCalledWith('/tickets', payload)
    expect(result).toEqual(out)
  })

  it('carries the read-only ticket_no business key on create and list', async () => {
    const out = { id: 2, ticket_no: 'TK-20260924-007', title: 't' }
    vi.mocked(http.post).mockResolvedValue(ok(out))
    const created = await createTicket({
      title: 't',
      category: 'incident' as const,
      priority: 'high' as const,
      description: '',
    })
    expect(created.ticket_no).toBe('TK-20260924-007')

    const page = { list: [out], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const listed = await listTickets()
    expect(listed.list[0].ticket_no).toBe('TK-20260924-007')
  })

  it('updates a ticket', async () => {
    vi.mocked(http.put).mockResolvedValue(ok({ id: 5 }))
    await updateTicket(5, { title: 't2', priority: 'low' })
    expect(http.put).toHaveBeenCalledWith('/tickets/5', { title: 't2', priority: 'low' })
  })

  it('assigns a ticket', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 5 }))
    await assignTicket(5, { assignee_id: 7 })
    expect(http.post).toHaveBeenCalledWith('/tickets/5/assign', { assignee_id: 7 })
  })

  it('runs simple transitions without a body', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 5 }))
    await acceptTicket(5)
    await processTicket(5)
    await closeTicket(5)
    await reopenTicket(5)
    await cancelTicket(5)
    expect(http.post).toHaveBeenNthCalledWith(1, '/tickets/5/accept')
    expect(http.post).toHaveBeenNthCalledWith(2, '/tickets/5/process')
    expect(http.post).toHaveBeenNthCalledWith(3, '/tickets/5/close')
    expect(http.post).toHaveBeenNthCalledWith(4, '/tickets/5/reopen')
    expect(http.post).toHaveBeenNthCalledWith(5, '/tickets/5/cancel')
  })

  it('completes a ticket with evidence ref', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 5 }))
    await doneTicket(5, { remark: 'fixed', exec_task_id: 9 })
    expect(http.post).toHaveBeenCalledWith('/tickets/5/done', { remark: 'fixed', exec_task_id: 9 })
  })

  it('adds a comment', async () => {
    const comment = { id: 1, author_id: 2, content: 'c', created_at: null }
    vi.mocked(http.post).mockResolvedValue(ok(comment))
    const result = await addTicketComment(5, 'c')
    expect(http.post).toHaveBeenCalledWith('/tickets/5/comments', { content: 'c' })
    expect(result).toEqual(comment)
  })

  it('adds a ref', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 1, ref_type: 'exec_task', ref_id: 9 }))
    await addTicketRef(5, { ref_type: 'exec_task', ref_id: 9 })
    expect(http.post).toHaveBeenCalledWith('/tickets/5/refs', { ref_type: 'exec_task', ref_id: 9 })
  })

  it('uploads attachments as multipart and returns the created list', async () => {
    const created = [{ id: 1, file_id: 3, filename: 'a.txt', size: 4, created_at: null }]
    vi.mocked(http.post).mockResolvedValue(ok({ ticket_id: 5, attachments: created }))
    const file = new File(['data'], 'a.txt', { type: 'text/plain' })
    const result = await uploadTicketAttachments(5, [file])
    expect(http.post).toHaveBeenCalledWith('/tickets/5/attachments', expect.any(FormData))
    expect(result).toEqual(created)
  })
})

describe('KB API (P3-2)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists articles with query params', async () => {
    const page = { list: [{ id: 1, title: 'a' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listArticles({ keyword: 'k', visibility: 'internal', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/kb/articles', {
      params: { keyword: 'k', visibility: 'internal', page: 1, size: 10 },
    })
    expect(result).toEqual(page)
  })

  it('fetches an article detail', async () => {
    const detail = { id: 3, content: 'x', tags: [] }
    vi.mocked(http.get).mockResolvedValue(ok(detail))
    const result = await getArticle(3)
    expect(http.get).toHaveBeenCalledWith('/kb/articles/3')
    expect(result).toEqual(detail)
  })

  it('creates an article', async () => {
    const out = { id: 4, title: 'a' }
    vi.mocked(http.post).mockResolvedValue(ok(out))
    const payload = { title: 'a', visibility: 'internal' as const, content: 'c' }
    const result = await createArticle(payload)
    expect(http.post).toHaveBeenCalledWith('/kb/articles', payload)
    expect(result).toEqual(out)
  })

  it('updates an article (new version)', async () => {
    vi.mocked(http.put).mockResolvedValue(ok({ id: 4 }))
    await updateArticle(4, { title: 'a2', content: 'c2', change_log: 'edit' })
    expect(http.put).toHaveBeenCalledWith('/kb/articles/4', { title: 'a2', content: 'c2', change_log: 'edit' })
  })

  it('deletes an article', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok({ id: 4, deleted: true }))
    await deleteArticle(4)
    expect(http.delete).toHaveBeenCalledWith('/kb/articles/4')
  })

  it('lists versions', async () => {
    const out = { article_id: 4, current_version: 2, list: [] as never[] }
    vi.mocked(http.get).mockResolvedValue(ok(out))
    const result = await listVersions(4)
    expect(http.get).toHaveBeenCalledWith('/kb/articles/4/versions')
    expect(result).toEqual(out)
  })

  it('fetches a specific version', async () => {
    const out = { article_id: 4, version: 2, content: 'old' }
    vi.mocked(http.get).mockResolvedValue(ok(out))
    const result = await getVersion(4, 2)
    expect(http.get).toHaveBeenCalledWith('/kb/articles/4/versions/2')
    expect(result).toEqual(out)
  })

  it('rolls back to a version', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 4 }))
    await rollbackArticle(4, 2)
    expect(http.post).toHaveBeenCalledWith('/kb/articles/4/rollback', { version: 2 })
  })

  it('lists the category tree', async () => {
    const out = { tree: [], total: 0 }
    vi.mocked(http.get).mockResolvedValue(ok(out))
    const result = await listCategories()
    expect(http.get).toHaveBeenCalledWith('/kb/categories')
    expect(result).toEqual(out)
  })

  it('creates a category', async () => {
    const out = { id: 8, parent_id: 0, name: 'n', sort: 0 }
    vi.mocked(http.post).mockResolvedValue(ok(out))
    const result = await createCategory({ name: 'n', parent_id: 0 })
    expect(http.post).toHaveBeenCalledWith('/kb/categories', { name: 'n', parent_id: 0 })
    expect(result).toEqual(out)
  })

  it('updates a category', async () => {
    vi.mocked(http.put).mockResolvedValue(ok({ id: 8 }))
    await updateCategory(8, { name: 'n2', parent_id: 0 })
    expect(http.put).toHaveBeenCalledWith('/kb/categories/8', { name: 'n2', parent_id: 0 })
  })

  it('deletes a category', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok({ id: 8, deleted: true }))
    await deleteCategory(8)
    expect(http.delete).toHaveBeenCalledWith('/kb/categories/8')
  })

  it('searches articles', async () => {
    const page = { list: [{ id: 1 }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await searchArticles('nginx', { page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/kb/search', { params: { q: 'nginx', page: 1, size: 10 } })
    expect(result).toEqual(page)
  })
})
