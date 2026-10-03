<template>
  <div class="wall">
    <h1 class="serif">{{ w.title }}</h1>
    <p>{{ w.note }}</p>
    <p class="tag">状态 {{ w.status }} · 认领人 {{ w.claimer || '—' }}</p>
    <p v-if="w.window_label" class="tag win" :class="{ closed: !w.window_open }">
      取货窗 {{ w.window_label }}（{{ w.window_tz }} 本地墙钟）· {{ w.window_text }}
    </p>
    <p v-if="err" class="err">{{ err }}</p>
    <input v-model="claimer" placeholder="你的名字" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button @click="claim">认领锁定</button>
      <button class="ghost" @click="release">释放</button>
      <button class="ghost" @click="fulfill">核销完成</button>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api, zhErr } from '../api'
const props = defineProps({ id: String })
const w = ref({})
const claimer = ref('访客')
const err = ref('')
async function load() { w.value = await api('/wishes/' + props.id) }
async function claim() {
  err.value=''; try { await api('/wishes/'+props.id+'/claim',{method:'POST',body:JSON.stringify({claimer:claimer.value})}); await load() } catch(e){ err.value=zhErr(e) }
}
async function release() {
  err.value=''; try { await api('/wishes/'+props.id+'/release',{method:'POST',body:'{}'}); await load() } catch(e){ err.value=zhErr(e) }
}
async function fulfill() {
  err.value=''
  try { await api('/wishes/'+props.id+'/fulfill',{method:'POST',body:'{}'}); await load() }
  catch(e){
    err.value = e.message === 'outside_pickup_window' && w.value.window_label
      ? `当前不在取货时间窗内（${w.value.window_label}，${w.value.window_tz} 本地墙钟），状态未变，可等窗内再核销`
      : zhErr(e)
  }
}
onMounted(load)
</script>
