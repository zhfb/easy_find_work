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
        <th style="padding:8px;">岗位</th><th>公司</th><th>薪资</th><th>评分</th><th>状态</th><th>时间</th><th>操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="a in apps" :key="a.id" style="border-bottom:1px solid #f0f0f0;">
          <td style="padding:8px;">{{ a.job_title || '#' + a.job_id }}</td>
          <td>{{ a.company }}</td><td>{{ a.salary_text }}</td>
          <td>{{ a.match_score ?? '—' }}</td>
          <td><span class="badge" :class="'st-' + a.status">{{ STATUS_LABELS[a.status] || a.status }}</span></td>
          <td style="font-size:12px;color:#888;">{{ a.applied_at || a.updated_at }}</td>
          <td>
            <select :value="a.status" @change="changeStatus(a, $event.target.value)" style="font-size:12px;padding:3px;">
              <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">{{ label }}</option>
            </select>
          </td>
        </tr>
        <tr v-if="!apps.length"><td colspan="7" style="text-align:center;color:#9ca3af;padding:30px;">暂无记录</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api/client.js'
import { STATUS_LABELS } from '../utils/dashboard.js'
const apps = ref([]); const status = ref(''); const taskId = ref('')
async function load() {
  const q = new URLSearchParams()
  if (status.value) q.set('status', status.value)
  if (taskId.value) q.set('task_id', taskId.value)
  apps.value = (await get('/api/applications?' + q.toString())).applications || []
}
async function changeStatus(a, s) {
  try { await post(`/api/applications/${a.id}/status`, { status: s }); await load() }
  catch (e) { alert('更新失败: ' + e.message) }
}
onMounted(load)
</script>
