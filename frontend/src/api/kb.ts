/**
 * Knowledge-base API (P3-2) — frontend/src/api/kb.ts
 * Contract: api-design-v3.md §6 (13 endpoints). Shapes @ backend/app/schemas/kb.py.
 * The service gates on `feature.kb` (default False -> HTTP 400 "feature disabled").
 */
import http from './http'
import type {
  Page,
  Result,
  KbArticleOut,
  KbArticleDetail,
  KbArticleQuery,
  KbArticleCreate,
  KbArticleUpdate,
  KbVersionListOut,
  KbVersionOut,
  KbCategoryListOut,
  KbCategoryOut,
  KbCategoryCreate,
  KbCategoryUpdate,
} from './types'

// ---------------------------------------------------------------- articles

export async function listArticles(params?: KbArticleQuery): Promise<Page<KbArticleOut>> {
  const { data } = await http.get<Result<Page<KbArticleOut>>>('/kb/articles', { params })
  return data.data
}

export async function getArticle(id: number): Promise<KbArticleDetail> {
  const { data } = await http.get<Result<KbArticleDetail>>(`/kb/articles/${id}`)
  return data.data
}

export async function createArticle(payload: KbArticleCreate): Promise<KbArticleOut> {
  const { data } = await http.post<Result<KbArticleOut>>('/kb/articles', payload)
  return data.data
}

export async function updateArticle(id: number, payload: KbArticleUpdate): Promise<KbArticleOut> {
  const { data } = await http.put<Result<KbArticleOut>>(`/kb/articles/${id}`, payload)
  return data.data
}

export async function deleteArticle(id: number): Promise<void> {
  await http.delete<Result<unknown>>(`/kb/articles/${id}`)
}

export async function listVersions(id: number): Promise<KbVersionListOut> {
  const { data } = await http.get<Result<KbVersionListOut>>(`/kb/articles/${id}/versions`)
  return data.data
}

export async function getVersion(id: number, version: number): Promise<KbVersionOut> {
  const { data } = await http.get<Result<KbVersionOut>>(`/kb/articles/${id}/versions/${version}`)
  return data.data
}

export async function rollbackArticle(id: number, version: number): Promise<KbArticleOut> {
  const { data } = await http.post<Result<KbArticleOut>>(`/kb/articles/${id}/rollback`, { version })
  return data.data
}

// ---------------------------------------------------------------- categories

export async function listCategories(): Promise<KbCategoryListOut> {
  const { data } = await http.get<Result<KbCategoryListOut>>('/kb/categories')
  return data.data
}

export async function createCategory(payload: KbCategoryCreate): Promise<KbCategoryOut> {
  const { data } = await http.post<Result<KbCategoryOut>>('/kb/categories', payload)
  return data.data
}

export async function updateCategory(id: number, payload: KbCategoryUpdate): Promise<KbCategoryOut> {
  const { data } = await http.put<Result<KbCategoryOut>>(`/kb/categories/${id}`, payload)
  return data.data
}

export async function deleteCategory(id: number): Promise<void> {
  await http.delete<Result<unknown>>(`/kb/categories/${id}`)
}

// ---------------------------------------------------------------- search

export async function searchArticles(
  q: string,
  params?: { page?: number; size?: number },
): Promise<Page<KbArticleOut>> {
  const { data } = await http.get<Result<Page<KbArticleOut>>>('/kb/search', {
    params: { q, ...params },
  })
  return data.data
}
