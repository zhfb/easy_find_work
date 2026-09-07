<template><div ref="el" style="width:100%;height:240px;"></div></template>
<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
const props = defineProps({ dates: Array, counts: Array })
const el = ref(null)
let chart = null
function render() {
  if (!chart) return
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 20, bottom: 28 },
    xAxis: { type: 'category', data: props.dates, axisLabel: { color: '#6b7280', fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#6b7280', fontSize: 11 } },
    series: [{
      type: 'line', smooth: true, data: props.counts,
      itemStyle: { color: '#1a1a2e' }, lineStyle: { color: '#1a1a2e', width: 2 },
      areaStyle: { color: 'rgba(26,26,46,0.06)' },
    }],
  })
}
onMounted(() => { chart = echarts.init(el.value); render(); window.addEventListener('resize', onResize) })
onBeforeUnmount(() => { window.removeEventListener('resize', onResize); if (chart) chart.dispose() })
function onResize() { if (chart) chart.resize() }
watch(() => [props.dates, props.counts], render, { deep: true })
</script>
