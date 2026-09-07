import { describe, it, expect } from 'vitest'
import { STATUS_LABELS, statusEntries, mapTrend } from '../src/utils/dashboard.js'

describe('dashboard utils', () => {
  it('状态标签覆盖 8 态', () => {
    expect(Object.keys(STATUS_LABELS)).toHaveLength(8)
    expect(STATUS_LABELS.applied).toBe('已投递')
  })
  it('statusEntries 转有序列表', () => {
    const rows = statusEntries({ applied: 3, skip: 2 })
    expect(rows[0]).toEqual({ key: 'applied', label: '已投递', value: 3 })
  })
  it('mapTrend 拆日期与数值', () => {
    const t = mapTrend([{ date: '2026-09-01', count: 2 }, { date: '2026-09-02', count: 0 }])
    expect(t.dates).toEqual(['2026-09-01', '2026-09-02'])
    expect(t.counts).toEqual([2, 0])
  })
})
