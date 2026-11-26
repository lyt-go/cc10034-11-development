/** 分组处置 / 稀有组放行单 / 分级分类获准范围相关接口。 */
import { request } from './client'

export type Board = Record<string, any>
export type ClassifyDetail = Record<string, any>

async function postJson(path: string, body: Record<string, unknown> = {}): Promise<Board> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  // 业务冲突也按 200 + { ok:false } 返回；HTTP 层异常时给出可读错误。
  if (!response.ok && response.status !== 409 && response.status !== 422) {
    throw new Error(`接口返回 ${response.status}`)
  }
  return (await response.json()) as Board
}

export async function listBatches(): Promise<{ items: Board[] }> {
  const response = await request('/api/group-release/batches')
  if (!response.ok) throw new Error('检查批次读取失败')
  return (await response.json()) as Promise<{ items: Board[] }>
}

export async function getBoard(checkId: number | string): Promise<Board> {
  const response = await request(`/api/group-release/batches/${checkId}`)
  if (!response.ok) throw new Error('分组核对结果读取失败')
  return (await response.json()) as Board
}

export function setThreshold(checkId: number | string, threshold: number): Promise<Board> {
  return postJson(`/api/group-release/batches/${checkId}/threshold`, { threshold })
}

export function recheck(checkId: number | string): Promise<Board> {
  return postJson(`/api/group-release/batches/${checkId}/recheck`, {})
}

export function isolateGroup(
  checkId: number | string,
  gid: string,
  reason: string,
): Promise<Board> {
  return postJson(`/api/group-release/batches/${checkId}/isolate`, { gid, reason })
}

export function mergeGroups(
  checkId: number | string,
  gids: string[],
  reason: string,
): Promise<Board> {
  return postJson(`/api/group-release/batches/${checkId}/merge`, { gids, reason })
}

export function addMember(checkId: number | string, gid: string): Promise<Board> {
  return postJson(`/api/group-release/batches/${checkId}/members`, { gid })
}

export function confirmDisposition(
  checkId: number | string,
  baseVersion?: number,
): Promise<Board> {
  return postJson(`/api/group-release/batches/${checkId}/confirm`, {
    base_version: baseVersion ?? null,
  })
}

export function submitOldDisposition(
  checkId: number | string,
  baseVersion = 1,
): Promise<Board> {
  return postJson(`/api/group-release/batches/${checkId}/submit-old`, {
    base_version: baseVersion,
  })
}

export async function getClassifyDetail(
  tagId: number | string,
  orderId?: string,
): Promise<ClassifyDetail> {
  const query = orderId ? `?order=${encodeURIComponent(orderId)}` : ''
  const response = await request(`/api/classify_tag/${tagId}/detail${query}`)
  if (!response.ok) throw new Error('分级分类详情读取失败')
  return (await response.json()) as ClassifyDetail
}

/** 获准范围下载地址：走后端 attachment 接口，浏览器 / Playwright 都能捕获下载。 */
export function approvedScopeUrl(tagId: number | string, orderId?: string): string {
  const query = orderId ? `?order=${encodeURIComponent(orderId)}` : ''
  return `/api/classify_tag/${tagId}/approved-scope/export${query}`
}

export function downloadApprovedScope(tagId: number | string, orderId?: string): void {
  const anchor = document.createElement('a')
  anchor.href = approvedScopeUrl(tagId, orderId)
  anchor.download = ''
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}
