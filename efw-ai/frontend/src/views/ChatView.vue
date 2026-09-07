<template>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">智能助手</h3>
    <div ref="log" style="height:420px;overflow-y:auto;background:#f9fafb;border-radius:8px;padding:12px;margin-bottom:10px;">
      <div v-for="(m, i) in messages" :key="i" :style="msgStyle(m.role)">
        <div class="muted" style="font-size:11px;">{{ m.role === 'user' ? '你' : '助手' }} · {{ m.created_at || '' }}</div>
        <div style="font-size:13px;white-space:pre-wrap;">{{ m.content }}</div>
      </div>
      <div v-if="streaming" style="font-size:13px;color:#555;">{{ streaming }}</div>
      <div v-if="pendingConfirm" style="border:1px solid #f59e0b;border-radius:8px;padding:10px;margin-top:8px;background:#fffbeb;">
        <div style="font-size:13px;">{{ pendingConfirm.text }}</div>
        <div style="margin-top:8px;display:flex;gap:6px;">
          <button class="btn ok" @click="confirm(true)">确认执行</button>
          <button class="btn" @click="pendingConfirm = null">取消</button>
        </div>
      </div>
    </div>
    <div style="display:flex;gap:8px;">
      <input v-model="input" placeholder="输入消息，如：创建一个投递任务，关键词 python，城市武汉" style="flex:1;padding:8px;border:1px solid #ddd;border-radius:6px;" @keyup.enter="send" />
      <button class="btn" :disabled="sending" @click="send">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { get, post } from '../api/client.js'
const messages = ref([]); const input = ref(''); const streaming = ref('')
const pendingConfirm = ref(null); const sending = ref(false); const log = ref(null)
async function send() {
  const text = input.value.trim(); if (!text || sending.value) return
  messages.value.push({ role: 'user', content: text }); input.value = ''
  sending.value = true; streaming.value = ''
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
    if (!resp.ok) throw new Error('请求失败')
    const reader = resp.body.getReader(); const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n'); buf = parts.pop()
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        let ev; try { ev = JSON.parse(part.slice(6)) } catch (e) { continue }
        if (ev.type === 'delta') { streaming.value += ev.text; scroll() }
        else if (ev.type === 'done') { messages.value.push({ role: 'assistant', content: streaming.value }); streaming.value = ''; scroll() }
        else if (ev.type === 'error') { messages.value.push({ role: 'assistant', content: '[错误] ' + ev.text }); streaming.value = ''; scroll() }
        else if (ev.type === 'confirm') { pendingConfirm.value = { id: ev.confirm_id, text: ev.text || '确认执行此操作？' } }
      }
    }
  } catch (e) { messages.value.push({ role: 'assistant', content: '[错误] ' + e.message }) }
  finally { sending.value = false }
}
async function confirm(ok) {
  if (!ok || !pendingConfirm.value) { pendingConfirm.value = null; return }
  const r = await post('/api/chat/confirm', { confirm_id: pendingConfirm.value.id })
  pendingConfirm.value = null
  messages.value.push({ role: 'assistant', content: JSON.stringify(r) })
  scroll()
}
function scroll() { nextTick(() => { if (log.value) log.value.scrollTop = log.value.scrollHeight }) }
function msgStyle(role) { return role === 'user' ? { textAlign: 'right' } : {} }
onMounted(async () => { messages.value = (await get('/api/chat/history')).messages || []; scroll() })
</script>
