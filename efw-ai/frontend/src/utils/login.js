export function loginStateMeta(state) {
  const map = {
    not_started:  { label: '未登录', tone: 'danger', action: '去登录' },
    starting:     { label: '正在启动浏览器…', tone: 'warning', action: null },
    waiting_login: { label: '请在弹出窗口完成登录', tone: 'warning', action: null },
    logged_in:    { label: '已登录', tone: 'success', action: '重新检测' },
    expired:      { label: '登录已过期', tone: 'warning', action: '重新登录' },
    timeout:      { label: '登录超时', tone: 'danger', action: '重试登录' },
    error:        { label: '浏览器启动失败', tone: 'danger', action: '重试' },
    closed:       { label: '窗口已关闭', tone: 'warning', action: '重新登录' },
  }
  return map[state] || { label: state, tone: 'neutral', action: null }
}
