import { describe, it, expect, vi, afterEach } from 'vitest'
import { get, post, put } from '../src/api/client.js'

function mockFetch(status, body, contentType = 'application/json') {
  global.fetch = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    statusText: 'Error',
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  })
}

afterEach(() => { vi.restoreAllMocks() })

describe('api client', () => {
  it('get 解析 JSON', async () => {
    mockFetch(200, { state: 'logged_in' })
    const data = await get('/api/auth/status')
    expect(data).toEqual({ state: 'logged_in' })
    expect(global.fetch).toHaveBeenCalledWith('/api/auth/status', expect.objectContaining({}))
  })

  it('get 非 2xx 抛出 detail', async () => {
    mockFetch(404, { detail: 'not found' })
    await expect(get('/api/x')).rejects.toThrow('not found')
  })

  it('post 携带 JSON body', async () => {
    mockFetch(200, { ok: true })
    await post('/api/auth/login', {})
    const [, opts] = global.fetch.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.body).toBe('{}')
  })

  it('put 携带 JSON body', async () => {
    mockFetch(200, { ok: true })
    await put('/api/config', { key: 'x', value: 'y' })
    const [, opts] = global.fetch.mock.calls[0]
    expect(opts.method).toBe('PUT')
    expect(opts.body).toBe('{"key":"x","value":"y"}')
  })
})
