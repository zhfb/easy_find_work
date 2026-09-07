<template>
  <div class="login-bar" :class="'tone-' + meta.tone">
    <span class="dot"></span>
    <span>{{ meta.label }}</span>
    <span v-if="lastChecked" class="muted">最后检测 {{ lastChecked }}</span>
    <button v-if="meta.action" class="btn" :disabled="busy" @click="act">
      {{ busy ? '处理中…' : meta.action }}
    </button>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { get, post } from '../api/client.js'
import { loginStateMeta } from '../utils/login.js'

const state = ref('not_started')
const lastChecked = ref('')
const busy = ref(false)
const meta = computed(() => loginStateMeta(state.value))
let timer = null

async function refresh() {
  try {
    const data = await get('/api/auth/status')
    state.value = data.state
    if (data.last_checked_at) lastChecked.value = data.last_checked_at.slice(11, 16)
  } catch (e) { /* 后端未起：保持当前状态 */ }
}
async function act() {
  busy.value = true
  try {
    if (state.value === 'logged_in') await post('/api/auth/check')
    else await post('/api/auth/login')
    await refresh()
  } catch (e) { alert('操作失败: ' + e.message) } finally { busy.value = false }
}
onMounted(() => { refresh(); timer = setInterval(refresh, 5000) })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.login-bar { display: flex; align-items: center; gap: 10px; background: var(--card);
  border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px;
  margin-bottom: 16px; font-size: 13px; flex-wrap: wrap; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.tone-danger .dot { background: var(--danger); } .tone-warning .dot { background: var(--warning); }
.tone-success .dot { background: var(--success); } .tone-neutral .dot { background: var(--muted); }
.muted { color: var(--muted); font-size: 12px; }
.btn { margin-left: auto; padding: 4px 14px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--primary); color: #fff; cursor: pointer; font-size: 12px; }
</style>
