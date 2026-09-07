<template>
  <div>
    <div class="cards">
      <StatCard label="今日投递" :value="today.delivered_today" :sub="`/ ${today.daily_limit} 配额`"
                :tone="today.remaining_ratio < 0.2 ? 'warning' : ''" />
      <StatCard label="运行中任务" :value="today.running_tasks" :sub="`暂停 ${today.paused_tasks}`" />
      <StatCard label="待跟进回复" :value="today.pending_followup" />
      <StatCard label="面试 + Offer" :value="today.interview_offer" />
      <StatCard label="累计成本" :value="'¥' + today.total_cost" :sub="`${today.total_tokens} tokens`" />
    </div>

    <div class="row">
      <div class="card" style="flex:2 1 400px;">
        <h3 style="font-size:14px;margin-bottom:10px;">近 7 天投递趋势</h3>
        <TrendChart :dates="trend.dates" :counts="trend.counts" />
      </div>
      <div class="card" style="flex:1 1 260px;">
        <h3 style="font-size:14px;margin-bottom:10px;">8 状态分布（累计）</h3>
        <StatusDistribution :entries="statusTotal" />
      </div>
    </div>

    <div class="row">
      <div class="card" style="flex:1 1 320px;">
        <h3 style="font-size:14px;margin-bottom:10px;">最近事件</h3>
        <EventTimeline :events="today.recent_events" />
      </div>
      <div class="card" style="flex:2 1 400px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <h3 style="font-size:14px;">任务列表</h3>
          <router-link to="/config" class="btn" style="font-size:12px;">+ 新建任务（配置页）</router-link>
        </div>
        <TaskTable :tasks="tasks" @action="taskAction" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api/client.js'
import StatCard from '../components/StatCard.vue'
import TrendChart from '../components/TrendChart.vue'
import StatusDistribution from '../components/StatusDistribution.vue'
import EventTimeline from '../components/EventTimeline.vue'
import TaskTable from '../components/TaskTable.vue'
import { statusEntries, mapTrend } from '../utils/dashboard.js'

const today = ref({ delivered_today: 0, daily_limit: 20, running_tasks: 0, paused_tasks: 0,
                    pending_followup: 0, interview_offer: 0, total_cost: 0, total_tokens: 0,
                    recent_events: [] })
const trend = ref({ dates: [], counts: [] })
const statusTotal = ref([])
const tasks = ref([])

async function load() {
  try {
    const [t, d] = await Promise.all([get('/api/dashboard/today'), get('/api/dashboard/deliveries?days=7')])
    today.value = t
    trend.value = mapTrend(d.trend)
    statusTotal.value = statusEntries(d.status_total)
    tasks.value = (await get('/api/tasks')).tasks || []
  } catch (e) { alert('加载失败: ' + e.message) }
}
async function taskAction(id, action) {
  try { await post(`/api/tasks/${id}/${action}`); await load() }
  catch (e) { alert('操作失败: ' + e.message) }
}
onMounted(load)
</script>

<style scoped>
.cards { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.row { display: flex; gap: 16px; flex-wrap: wrap; }
</style>
