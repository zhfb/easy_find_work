import { describe, it, expect } from 'vitest'
import { buildTaskPayload } from '../src/utils/tasks.js'

describe('buildTaskPayload', () => {
  it('方向+城市生成完整 payload（关键词合并、默认值）', () => {
    const { errors, payload } = buildTaskPayload({
      direction: '云计算运维',
      extraKeywords: 'K8s, Docker，linux',
      city: '武汉',
      mode: 'auto',
    })
    expect(errors).toEqual([])
    expect(payload.name).toBe('云计算运维·武汉')
    expect(JSON.parse(payload.keywords)).toEqual(['云计算运维', 'K8s', 'Docker', 'linux'])
    expect(payload.city).toBe('武汉')
    expect(payload.mode).toBe('auto')
    expect(payload.daily_limit).toBe(20)
    expect(payload.max_deliveries).toBe(50)
    expect(payload.match_threshold).toBe(7.0)
    expect(payload.rules).toBe('{}')
  })

  it('semi 模式与自定义数值透传', () => {
    const { payload } = buildTaskPayload({
      direction: '运维开发',
      city: '上海',
      mode: 'semi',
      dailyLimit: 15,
      maxDeliveries: 30,
      matchThreshold: 6.5,
      salaryMin: 18,
    })
    expect(payload.mode).toBe('semi')
    expect(payload.daily_limit).toBe(15)
    expect(payload.max_deliveries).toBe(30)
    expect(payload.match_threshold).toBe(6.5)
    expect(JSON.parse(payload.rules)).toEqual({ salary_min: 18 })
  })

  it('缺方向或城市返回校验错误', () => {
    expect(buildTaskPayload({ city: '武汉' }).errors).toContain('请填写岗位方向')
    expect(buildTaskPayload({ direction: '运维' }).errors).toContain('请填写城市')
  })

  it('自定义任务名称优先', () => {
    const { payload } = buildTaskPayload({ direction: '运维', city: '武汉', name: '我的求职' })
    expect(payload.name).toBe('我的求职')
  })

  it('薪资下限为空/非正数不进 rules', () => {
    const a = buildTaskPayload({ direction: '运维', city: '武汉', salaryMin: 0 })
    expect(JSON.parse(a.payload.rules)).toEqual({})
    const b = buildTaskPayload({ direction: '运维', city: '武汉' })
    expect(JSON.parse(b.payload.rules)).toEqual({})
  })
})
