import { describe, it, expect } from 'vitest'
import { loginStateMeta } from '../src/utils/login.js'

describe('loginStateMeta', () => {
  it('覆盖 8 个状态', () => {
    for (const s of ['not_started', 'starting', 'waiting_login', 'logged_in',
                     'expired', 'timeout', 'error', 'closed']) {
      const meta = loginStateMeta(s)
      expect(meta.label).toBeTruthy()
      expect(meta.tone).toBeTruthy()
    }
  })
  it('未登录显示去登录动作', () => {
    expect(loginStateMeta('not_started')).toEqual(
      expect.objectContaining({ label: '未登录', action: '去登录' }))
  })
  it('已登录显示重新检测动作', () => {
    expect(loginStateMeta('logged_in').action).toBe('重新检测')
  })
  it('未知状态回退中性', () => {
    expect(loginStateMeta('whatever').tone).toBe('neutral')
  })
})
