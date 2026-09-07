<template>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">半自动清单（{{ apps.length }} 条待确认）</h3>
    <div v-for="a in apps" :key="a.id" style="border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <div>
          <b>{{ a.job_title || '#' + a.job_id }}</b>
          <span class="muted" style="margin-left:8px;">{{ a.company }} · {{ a.salary_text }}</span>
          <span class="muted" style="display:block;font-size:12px;">评分 {{ a.match_score ?? '—' }} · {{ a.llm_reason }}</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn ok" @click="confirm(a, 'applied')">确认投递</button>
          <button class="btn" @click="confirm(a, 'skip')">跳过</button>
          <button class="btn" @click="regenerate(a)">重写消息</button>
        </div>
      </div>
      <div v-if="a.message" style="margin-top:8px;font-size:12px;color:#555;background:#f9fafb;padding:8px;border-radius:6px;">{{ a.message }}</div>
      <div v-if="candidates[a.id]" style="margin-top:8px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="(m, i) in candidates[a.id]" :key="i" style="font-size:12px;background:#f9fafb;padding:8px;border-radius:6px;display:flex;gap:8px;align-items:center;">
          <span style="flex:1;">{{ m }}</span>
          <button class="btn ok" @click="confirm(a, 'applied', m)">选用</button>
        </div>
      </div>
    </div>
    <div v-if="!apps.length" style="text-align:center;color:#9ca3af;padding:30px;">暂无待确认岗位</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api/client.js'
const apps = ref([]); const candidates = ref({})
async function load() { apps.value = (await get('/api/applications?status=pending_manual&limit=100')).applications || [] }
async function confirm(a, status, message) {
  await post(`/api/applications/${a.id}/status`, { status, detail: message || a.message || '' })
  candidates.value[a.id] = null; await load()
}
async function regenerate(a) {
  const r = await post(`/api/applications/${a.id}/regenerate-message`)
  candidates.value[a.id] = r.messages || []
}
onMounted(load)
</script>
