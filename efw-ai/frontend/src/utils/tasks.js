// 新建任务表单 → POST /api/tasks payload 组装
// 字段：岗位方向/附加关键词 → keywords[]；期望月薪下限 → rules.salary_min

export function buildTaskPayload(form = {}) {
  const errors = []
  const direction = String(form.direction || '').trim()
  const city = String(form.city || '').trim()
  if (!direction) errors.push('请填写岗位方向')
  if (!city) errors.push('请填写城市')
  if (errors.length) return { errors, payload: null }

  const extra = String(form.extraKeywords || '')
    .split(/[,，、]/)
    .map((s) => s.trim())
    .filter(Boolean)
  const keywords = [direction, ...extra]

  const rules = {}
  const salaryMin = Number(form.salaryMin)
  if (Number.isFinite(salaryMin) && salaryMin > 0) rules.salary_min = salaryMin

  return {
    errors,
    payload: {
      name: String(form.name || '').trim() || `${direction}·${city}`,
      keywords: JSON.stringify(keywords),
      city,
      mode: form.mode === 'semi' ? 'semi' : 'auto',
      max_deliveries: Number(form.maxDeliveries) > 0 ? Number(form.maxDeliveries) : 50,
      daily_limit: Number(form.dailyLimit) > 0 ? Number(form.dailyLimit) : 20,
      match_threshold: Number(form.matchThreshold) > 0 ? Number(form.matchThreshold) : 7.0,
      rules: JSON.stringify(rules),
    },
  }
}
