export const STATUS_LABELS = {
  skip: '跳过', pending_manual: '待人工确认', applied: '已投递', responded: 'HR 回复',
  interview: '面试', offer: 'Offer', rejected: '被拒', withdrawn: '撤回',
}
export function statusEntries(dist) {
  return Object.entries(dist || {}).map(([key, value]) => ({
    key, label: STATUS_LABELS[key] || key, value,
  }))
}
export function mapTrend(trend) {
  return { dates: (trend || []).map(t => t.date), counts: (trend || []).map(t => t.count) }
}
