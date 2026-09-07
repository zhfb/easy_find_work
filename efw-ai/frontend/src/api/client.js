async function request(url, options = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const data = await resp.json()
      if (data && data.detail) detail = data.detail
    } catch (e) { /* 非 JSON 错误体，保留 statusText */ }
    throw new Error(detail)
  }
  const ct = resp.headers.get('content-type') || ''
  return ct.includes('application/json') ? resp.json() : resp.text()
}

export const get = (url) => request(url)
export const post = (url, body) =>
  request(url, { method: 'POST', body: body ? JSON.stringify(body) : undefined })
