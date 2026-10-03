<template>
  <div class="wall">
    <h1 class="serif">发愿望</h1>
    <input v-model="title" placeholder="标题" />
    <textarea v-model="note" rows="4" placeholder="备注" />
    <p class="tag">{{ defaultHint }}</p>
    <label class="check"><input type="checkbox" v-model="custom" /> 自定义取货窗（发布后落窗快照）</label>
    <div v-if="custom">
      <div class="days">
        <label v-for="(d,i) in dayNames" :key="i"><input type="checkbox" :value="i" v-model="days" /> {{ d }}</label>
      </div>
      <div style="display:flex;gap:8px">
        <input type="time" v-model="start" />
        <input type="time" v-model="end" />
      </div>
    </div>
    <p v-if="err" class="err">{{ err }}</p>
    <button @click="submit">发布</button>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, zhErr } from '../api'
const router = useRouter()
const dayNames = ['周一','周二','周三','周四','周五','周六','周日']
const title = ref('')
const note = ref('')
const custom = ref(false)
const days = ref([])
const start = ref('09:00')
const end = ref('21:00')
const defaultHint = ref('')
const err = ref('')
onMounted(async () => {
  const s = await api('/settings')
  days.value = (s.pickup_days || '').split(',').filter(x => x !== '').map(Number)
  start.value = s.pickup_start || '09:00'
  end.value = s.pickup_end || '21:00'
  const r = await api('/rules')
  defaultHint.value = r.pickup_window || ''
})
async function submit() {
  err.value = ''
  const body = { title: title.value, note: note.value }
  if (custom.value) body.window = { days: days.value, start: start.value, end: end.value }
  try {
    const r = await api('/wishes', { method: 'POST', body: JSON.stringify(body) })
    router.push('/wishes/' + r.id)
  } catch (e) { err.value = zhErr(e) }
}
</script>
