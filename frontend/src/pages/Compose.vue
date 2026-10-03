<template>
  <div class="wall">
    <h1 class="serif">发愿望</h1>
    <input v-model="title" placeholder="标题" />
    <textarea v-model="note" rows="4" placeholder="备注" />

    <details class="card" style="cursor:default;padding:12px 16px">
      <summary>自定义取货窗（默认跟随规则页{{ defSummary ? '：' + defSummary : '' }}）</summary>
      <label class="chk" style="margin:10px 0">
        <input type="checkbox" v-model="custom" />为该愿望自定义取货窗
      </label>
      <fieldset :disabled="!custom" style="border:0;padding:0;margin:0">
        <div class="weekdays">
          <label v-for="d in 7" :key="d-1" class="chk">
            <input type="checkbox" :value="d-1" v-model="win.weekdays" />{{ names[d-1] }}
          </label>
        </div>
        <div class="hours">
          <label>开始小时<input type="number" min="0" max="24" v-model.number="win.start_hour" /></label>
          <label>结束小时<input type="number" min="0" max="24" v-model.number="win.end_hour" /></label>
        </div>
        <label>时区（留空使用默认时区）
          <input list="tz-list" v-model="win.timezone" placeholder="默认 Asia/Shanghai" />
        </label>
        <datalist id="tz-list">
          <option v-for="tz in tzs" :key="tz" :value="tz"></option>
        </datalist>
        <p class="tag">含起点不含终点；结束小时必须大于开始小时。</p>
      </fieldset>
    </details>

    <p v-if="err" class="err">{{ err }}</p>
    <button @click="submit">发布</button>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
const router = useRouter()
const title = ref('')
const note = ref('')
const err = ref('')
const custom = ref(false)
const names = ['周一','周二','周三','周四','周五','周六','周日']
const tzs = ['Asia/Shanghai','Asia/Tokyo','Asia/Singapore','UTC','Europe/London','America/New_York','America/Los_Angeles']
const win = ref({ weekdays: [5, 6], start_hour: 9, end_hour: 18, timezone: '' })
const defSummary = ref('')

async function submit() {
  err.value = ''
  const payload = { title: title.value, note: note.value }
  if (custom.value) {
    payload.pickup_window = {
      weekdays: win.value.weekdays,
      start_hour: win.value.start_hour,
      end_hour: win.value.end_hour,
    }
    if (win.value.timezone) payload.pickup_window.timezone = win.value.timezone
  }
  try {
    const r = await api('/wishes', { method: 'POST', body: JSON.stringify(payload) })
    router.push('/wishes/' + r.id)
  } catch (e) { err.value = e.message }
}

onMounted(async () => {
  const r = await api('/rules/pickup-window')
  const wd = r.window.weekdays.map(d => names[d]).join('、')
  defSummary.value = `${wd} ${String(r.window.start_hour).padStart(2,'0')}:00–${String(r.window.end_hour).padStart(2,'0')}:00（${r.timezone}）`
})
</script>
<style scoped>
.weekdays { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0; }
.chk { display: flex; align-items: center; gap: 4px; font-size: 14px; white-space: nowrap; }
.chk input { width: auto; margin: 0; }
.hours { display: flex; gap: 12px; }
.hours label { flex: 1; }
details[disabled] { opacity: .6; }
</style>
