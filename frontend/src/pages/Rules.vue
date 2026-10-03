<template>
  <div class="wall">
    <h1 class="serif">规则</h1>
    <ul>
      <li v-for="(v,k) in rules" :key="k"><strong>{{ k }}</strong>：{{ v }}</li>
    </ul>
    <h2 class="serif">默认取货窗</h2>
    <div class="days">
      <label v-for="(d,i) in dayNames" :key="i"><input type="checkbox" :value="i" v-model="days" /> {{ d }}</label>
    </div>
    <div style="display:flex;gap:8px">
      <input type="time" v-model="start" />
      <input type="time" v-model="end" />
    </div>
    <input v-model="tz" placeholder="时区（IANA，如 Asia/Shanghai）；窗按该时区本地墙钟解释，不按 UTC" />
    <button @click="save">保存默认窗</button>
    <p v-if="msg" :class="ok ? 'tag' : 'err'">{{ msg }}</p>
    <p class="tag">仅影响之后发布的愿望；已发布愿望的窗快照不被改写。</p>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api, zhErr } from '../api'
const dayNames = ['周一','周二','周三','周四','周五','周六','周日']
const rules = ref({})
const days = ref([])
const start = ref('09:00')
const end = ref('21:00')
const tz = ref('Asia/Shanghai')
const msg = ref('')
const ok = ref(false)
async function load() {
  rules.value = await api('/rules')
  const s = await api('/settings')
  days.value = (s.pickup_days || '').split(',').filter(x => x !== '').map(Number)
  start.value = s.pickup_start || '09:00'
  end.value = s.pickup_end || '21:00'
  tz.value = s.pickup_timezone || 'Asia/Shanghai'
}
async function save() {
  msg.value = ''
  try {
    await api('/settings/window', { method: 'PUT', body: JSON.stringify({ days: days.value, start: start.value, end: end.value, tz: tz.value }) })
    ok.value = true; msg.value = '已保存默认取货窗'
    await load()
  } catch (e) { ok.value = false; msg.value = zhErr(e) }
}
onMounted(load)
</script>
