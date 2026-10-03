<template>
  <div class="wall">
    <h1 class="serif">规则</h1>

    <section class="card" style="cursor:default">
      <h3>默认取货时间窗</h3>
      <p class="tag">星期集合 + 每日小时段，发愿望默认跟随此窗并固化快照</p>

      <div class="weekdays">
        <label v-for="d in 7" :key="d-1" class="chk">
          <input type="checkbox" :value="d-1" v-model="form.weekdays" />{{ names[d-1] }}
        </label>
      </div>
      <div class="hours">
        <label>开始小时
          <input type="number" min="0" max="24" v-model.number="form.start_hour" />
        </label>
        <label>结束小时
          <input type="number" min="0" max="24" v-model.number="form.end_hour" />
        </label>
      </div>
      <label>时区（IANA，按本地墙钟判定）
        <input list="tz-list" v-model="form.timezone" placeholder="Asia/Shanghai" />
      </label>
      <datalist id="tz-list">
        <option v-for="tz in tzs" :key="tz" :value="tz"></option>
      </datalist>

      <div style="display:flex;gap:8px;align-items:center;margin-top:8px">
        <button @click="save">保存默认窗</button>
        <span v-if="msg" class="ok">{{ msg }}</span>
      </div>
      <p v-if="err" class="err">{{ err }}</p>

      <ul class="explain">
        <li>取货时间窗按所选时区的<strong>本地墙钟</strong>判定，24 小时制整点，含起点不含终点；结束小时必须大于开始小时，不支持跨午夜。</li>
        <li><strong>认领任何时间都可以；仅核销（fulfill）必须在窗内。</strong></li>
        <li>修改默认窗/时区<strong>不会改写已有愿望</strong>——每个愿望发布时固化自己的窗快照。</li>
      </ul>
    </section>

    <ul>
      <li v-for="(v,k) in rules" :key="k"><strong>{{ k }}</strong>：{{ v }}</li>
    </ul>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rules = ref({})
const names = ['周一','周二','周三','周四','周五','周六','周日']
const tzs = ['Asia/Shanghai','Asia/Tokyo','Asia/Singapore','UTC','Europe/London','America/New_York','America/Los_Angeles']
const form = ref({ weekdays: [], start_hour: 9, end_hour: 18, timezone: 'Asia/Shanghai' })
const err = ref(''); const msg = ref('')
async function load() {
  const r = await api('/rules/pickup-window')
  form.value = { weekdays: r.window.weekdays, start_hour: r.window.start_hour, end_hour: r.window.end_hour, timezone: r.timezone }
}
async function save() {
  err.value = ''; msg.value = ''
  try {
    const r = await api('/rules/pickup-window', { method: 'PUT', body: JSON.stringify(form.value) })
    form.value = { weekdays: r.window.weekdays, start_hour: r.window.start_hour, end_hour: r.window.end_hour, timezone: r.timezone }
    msg.value = '已保存，仅影响此后发布的愿望'
  } catch (e) { err.value = e.message }
}
onMounted(async () => { await load(); rules.value = await api('/rules') })
</script>
<style scoped>
.weekdays { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0; }
.chk { display: flex; align-items: center; gap: 4px; font-size: 14px; white-space: nowrap; }
.chk input { width: auto; margin: 0; }
.hours { display: flex; gap: 12px; }
.hours label { flex: 1; }
.explain { padding-left: 18px; font-size: 13px; color: var(--muted); line-height: 1.7; }
.ok { color: #3a7d44; font-size: 13px; }
</style>
