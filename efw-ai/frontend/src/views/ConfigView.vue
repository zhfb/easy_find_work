<template>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">新建投递任务</h3>
    <div style="display:flex;flex-direction:column;gap:10px;">
      <input v-model="taskForm.name" placeholder="任务名称（留空自动生成）" style="padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
      <input v-model="taskForm.direction" placeholder="岗位方向（必填，如：云计算运维）" style="padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
      <input v-model="taskForm.extraKeywords" placeholder="附加关键词（逗号分隔，可选）" style="padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
      <input v-model="taskForm.city" placeholder="城市（必填，如：武汉）" style="padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input v-model.number="taskForm.dailyLimit" type="number" placeholder="日限额（默认 20）" style="flex:1 1 140px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
        <input v-model.number="taskForm.maxDeliveries" type="number" placeholder="投递总量（默认 50）" style="flex:1 1 140px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
        <input v-model.number="taskForm.matchThreshold" type="number" step="0.1" placeholder="评分阈值（默认 7.0）" style="flex:1 1 140px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
        <input v-model.number="taskForm.salaryMin" type="number" placeholder="期望月薪下限 k（可选）" style="flex:1 1 140px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
      </div>
      <select v-model="taskForm.mode" style="padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;">
        <option value="auto">自动投递：AI 全流程决策并直接投递</option>
        <option value="semi">人工确认：AI 筛选后排入半自动清单，你确认后才投</option>
      </select>
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <button class="btn" @click="createTask">创建任务</button>
        <span v-if="taskOk" style="color:#389E0D;font-size:12px;">创建成功，可去任务详情启动</span>
        <span v-if="taskError" style="color:#EA6668;font-size:12px;">{{ taskError }}</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">我的任务</h3>
    <div v-if="!tasks.length" style="font-size:13px;color:#6B7280;">暂无任务，用上方表单新建一个</div>
    <div v-for="t in tasks" :key="t.id" @click="$router.push('/tasks/' + t.id)"
         style="display:flex;gap:10px;align-items:center;padding:10px 12px;border:1px solid #E4E3DD;border-radius:8px;margin-bottom:8px;cursor:pointer;background:#FBFBFA;flex-wrap:wrap;">
      <span style="font-weight:600;font-size:13px;">{{ t.name }}</span>
      <span style="font-size:12px;color:#6B7280;">{{ JSON.parse(t.keywords || '[]').join(' / ') }}</span>
      <span style="font-size:12px;color:#6B7280;">{{ t.city }}</span>
      <span style="font-size:12px;padding:1px 8px;border-radius:999px;background:rgba(158,172,234,0.2);">{{ t.mode === 'semi' ? '人工确认' : '自动投递' }}</span>
      <span style="font-size:12px;color:#374151;">{{ statusLabel(t.status) }}</span>
      <span style="font-size:12px;color:#6B7280;">日限额 {{ t.daily_limit }}</span>
      <span style="font-size:12px;color:#9EACEA;margin-left:auto;">详情 →</span>
    </div>
  </div>

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
import { get, post, put } from '../api/client.js'
import { buildTaskPayload } from '../utils/tasks.js'

const config = ref({})
const profile = ref({})
const tasks = ref([])
const taskOk = ref('')
const taskError = ref('')
const taskForm = ref({ name: '', direction: '', extraKeywords: '', city: '',
  mode: 'auto', dailyLimit: 20, maxDeliveries: 50, matchThreshold: 7.0, salaryMin: null })

const STATUS_LABEL = { pending: '待启动', running: '运行中', paused: '已暂停', finished: '已完成', stopped: '已停止', failed: '失败' }
function statusLabel(s) { return STATUS_LABEL[s] || s }

async function load() {
  config.value = await get('/api/config')
  try { profile.value = await get('/api/profile') } catch (e) { profile.value = {} }
  try { tasks.value = (await get('/api/tasks')).tasks || [] } catch (e) { tasks.value = [] }
}
function save(key, value) { put('/api/config', { key, value }).then(load).catch(e => alert('保存失败: ' + e.message)) }
function saveProfile() { put('/api/profile', profile.value).then(load).catch(e => alert('保存失败: ' + e.message)) }

async function createTask() {
  taskOk.value = ''; taskError.value = ''
  const { errors, payload } = buildTaskPayload(taskForm.value)
  if (errors.length) { taskError.value = errors.join('；'); return }
  try {
    await post('/api/tasks', payload)
    taskOk.value = '创建成功，可去任务详情启动'
    taskForm.value = { name: '', direction: '', extraKeywords: '', city: '',
      mode: 'auto', dailyLimit: 20, maxDeliveries: 50, matchThreshold: 7.0, salaryMin: null }
    await load()
  } catch (e) { taskError.value = '创建失败: ' + e.message }
}
onMounted(load)
</script>
