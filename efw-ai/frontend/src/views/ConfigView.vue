<template>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">系统配置</h3>
    <div style="display:flex;flex-direction:column;gap:10px;">
      <div v-for="(v, k) in config" :key="k" style="display:flex;gap:8px;align-items:center;">
        <span style="flex:0 0 160px;font-size:13px;">{{ k }}</span>
        <input :value="v" @change="save(k, $event.target.value)" style="flex:1;padding:6px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
      </div>
      <button class="btn" @click="load">刷新配置</button>
    </div>
  </div>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">求职画像</h3>
    <div style="display:flex;flex-direction:column;gap:10px;">
      <textarea v-model="profile.skills" placeholder="技能（逗号分隔）" style="padding:8px;border:1px solid #ddd;border-radius:6px;"></textarea>
      <input v-model.number="profile.experience_years" placeholder="经验年限" style="padding:8px;border:1px solid #ddd;border-radius:6px;" />
      <input v-model="profile.target_city" placeholder="目标城市" style="padding:8px;border:1px solid #ddd;border-radius:6px;" />
      <textarea v-model="profile.resume_summary" placeholder="简历摘要" style="padding:8px;border:1px solid #ddd;border-radius:6px;min-height:80px;"></textarea>
      <button class="btn" @click="saveProfile">保存画像</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, put } from '../api/client.js'
const config = ref({}); const profile = ref({})
async function load() {
  config.value = await get('/api/config')
  try { profile.value = await get('/api/profile') } catch (e) { profile.value = {} }
}
function save(key, value) { put('/api/config', { key, value }).then(load).catch(e => alert('保存失败: ' + e.message)) }
function saveProfile() { put('/api/profile', profile.value).then(load).catch(e => alert('保存失败: ' + e.message)) }
onMounted(load)
</script>
