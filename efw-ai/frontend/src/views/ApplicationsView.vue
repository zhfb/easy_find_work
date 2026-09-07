<template>
  <div class="card">
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
      <select v-model="status" @change="load" style="padding:6px;border:1px solid #ddd;border-radius:6px;">
        <option value="">全部状态</option>
        <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">{{ label }}</option>
      </select>
      <input v-model.number="taskId" placeholder="任务 ID 过滤" style="padding:6px;border:1px solid #ddd;border-radius:6px;width:110px;" @change="load" />
      <button class="btn" @click="load">刷新</button>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead><tr style="border-bottom:2px solid #eee;text-align:left;color:#666;">
        <th style="padding:8px;">岗位</th><th>公司</th><th>薪资</th><th>评分</th><th>状态</th><th>时间</th><th>打招呼消息</th><th>操作</th>
      </tr></thead>
      <tbody>
        <template v-for="a in apps" :key="a.id">
          <tr style="border-bottom:1px solid #f0f0f0;">
            <td style="padding:8px;">{{ a.job_title || '#' + a.job_id }}</td>
            <td>{{ a.company }}</td><td>{{ a.salary_text }}</td>
            <td>{{ a.match_score ?? '—' }}</td>
            <td><span class="badge" :class="'st-' + a.status">{{ STATUS_LABELS[a.status] || a.status }}</span></td>
            <td style="font-size:12px;color:#888;">{{ a.applied_at || a.updated_at }}</td>
            <td>
              <button class="btn" style="padding:3px 10px;font-size:12px;" @click="toggleMsg(a.id)">{{ expandedId === a.id ? '收起' : '查看' }}</button>
            </td>
            <td>
              <select :value="a.status" @change="changeStatus(a, $event.target.value)" style="font-size:12px;padding:3px;">
                <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">{{ label }}</option>
              </select>
            </td>
          </tr>
          <tr v-if="expandedId === a.id" style="background:#FBFBFA;border-bottom:1px solid #f0f0f0;">
            <td colspan="8" style="padding:10px 12px;">
              <div style="font-size:12px;color:#6B7280;margin-bottom:6px;">投递给 HR 的自我介绍（由 AI 基于你的求职画像 + 该岗位生成）：</div>
              <div style="font-size:13px;color:#1A1B1C;background:#fff;border:1px solid #E4E3DD;border-radius:8px;padding:10px;min-height:40px;white-space:pre-wrap;">{{ a.message || '（投递时未生成消息）' }}</div>
              <div style="margin-top:8px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                <button class="btn" style="padding:4px 12px;font-size:12px;" @click="regenerate(a)" :disabled="a.regenerating">AI 重新生成</button>
                <span v-if="a.regenerating" style="font-size:12px;color:#6B7280;">生成中…</span>
                <span v-if="a.msgNote" style="font-size:12px;color:#389E0D;">{{ a.msgNote }}</span>
                <span v-if="a.msgError" style="font-size:12px;color:#EA6668;">{{ a.msgError }}</span>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="!apps.length"><td colspan="8" style="text-align:center;color:#9ca3af;padding:30px;">暂无记录</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api/client.js'
import { STATUS_LABELS } from '../utils/dashboard.js'
const apps = ref([]); const status = ref(''); const taskId = ref('')
const expandedId = ref(null)
async function load() {
  const q = new URLSearchParams()
  if (status.value) q.set('status', status.value)
  if (taskId.value) q.set('task_id', taskId.value)
  apps.value = (await get('/api/applications?' + q.toString())).applications || []
}
function toggleMsg(id) { expandedId.value = expandedId.value === id ? null : id }
async function changeStatus(a, s) {
  try { await post(`/api/applications/${a.id}/status`, { status: s }); await load() }
  catch (e) { alert('更新失败: ' + e.message) }
}
async function regenerate(a) {
  a.regenerating = true; a.msgNote = ''; a.msgError = ''
  try {
    const { messages } = await post(`/api/applications/${a.id}/regenerate-message`)
    if (messages && messages.length) {
      a.message = messages[0]
      a.msgNote = '已生成新消息（共 ' + messages.length + ' 条候选，已用第 1 条更新此记录）'
    } else {
      a.msgError = '无可生成消息：请先完善配置页「求职画像」并确认岗位存在'
    }
  } catch (e) { a.msgError = '生成失败: ' + e.message }
  a.regenerating = false
}
onMounted(load)
</script>
