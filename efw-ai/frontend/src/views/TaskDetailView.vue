<template>
  <div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <div>
          <h3 style="font-size:15px;">{{ task.name || '任务 #' + id }}</h3>
          <span class="muted" style="font-size:12px;">模式 {{ task.mode }} · 状态 <b>{{ task.status }}</b> · 累计 {{ task.application_count }} 条评估</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button v-if="['pending','paused','stopped'].includes(task.status)" class="btn" @click="act('start')">启动</button>
          <button v-if="task.status==='running'" class="btn" @click="act('pause')">暂停</button>
          <button v-if="task.status==='paused'" class="btn" @click="act('resume')">继续</button>
          <button v-if="task.status==='interrupted'" class="btn" @click="act('resume-after-crash')">崩溃续跑</button>
          <button v-if="['running','paused'].includes(task.status)" class="btn danger" @click="act('stop')">停止</button>
        </div>
      </div>
      <div v-if="sseState" class="muted" style="font-size:12px;margin-top:8px;">{{ sseState }}</div>
      <div v-if="events.length" style="margin-top:10px;max-height:140px;overflow-y:auto;font-size:12px;background:#f9fafb;padding:10px;border-radius:8px;">
        <div v-for="(e, i) in events" :key="i">{{ e }}</div>
      </div>
    </div>
    <div class="card">
      <h3 style="font-size:14px;margin-bottom:10px;">岗位评估（最近 100 条）</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="border-bottom:2px solid #eee;text-align:left;color:#666;">
          <th style="padding:8px;">岗位</th><th>公司</th><th>薪资</th><th>决策</th><th>评分</th><th>状态</th><th>理由</th>
        </tr></thead>
        <tbody>
          <tr v-for="a in apps" :key="a.id" style="border-bottom:1px solid #f0f0f0;">
            <td style="padding:8px;">{{ a.job_title || '#' + a.job_id }}</td>
            <td>{{ a.company }}</td><td>{{ a.salary_text }}</td>
            <td>{{ a.decision }}</td><td>{{ a.match_score ?? '—' }}</td>
            <td>{{ a.status }}</td>
            <td style="font-size:12px;color:#666;max-width:280px;">{{ a.llm_reason }}</td>
          </tr>
          <tr v-if="!apps.length"><td colspan="7" style="text-align:center;color:#9ca3af;padding:30px;">暂无评估记录</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { get, post } from '../api/client.js'
const route = useRoute(); const id = route.params.id
const task = ref({}); const apps = ref([]); const events = ref([]); const sseState = ref('')
let es = null
async function load() {
  task.value = await get('/api/tasks/' + id)
  apps.value = (await get('/api/applications?task_id=' + id + '&limit=100')).applications || []
}
async function act(action) { await post(`/api/tasks/${id}/${action}`); await load() }
function connect() {
  es = new EventSource(`/api/tasks/${id}/events`)
  es.onopen = () => { sseState.value = '已连接实时进度' }
  es.onmessage = (e) => {
    try { const d = JSON.parse(e.data); events.value.unshift(JSON.stringify(d)); if (events.value.length > 50) events.value.pop() }
    catch (err) { events.value.unshift(e.data) }
  }
  es.onerror = () => { sseState.value = '连接中断，重连中…' }
}
onMounted(() => { load(); connect() })
onBeforeUnmount(() => { if (es) es.close() })
</script>
