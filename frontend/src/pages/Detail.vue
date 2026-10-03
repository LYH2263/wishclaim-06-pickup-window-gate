<template>
  <div class="wall">
    <h1 class="serif">{{ w.title }}</h1>
    <p>{{ w.note }}</p>
    <p class="tag">状态 {{ w.status }} · 认领人 {{ w.claimer || '—' }}</p>

    <section v-if="w.pickup_state" class="winbox">
      <span :class="['dot', w.pickup_state.is_open ? 'open' : 'closed']"></span>
      <span class="tag">{{ w.pickup_state.human }}（{{ w.pickup_state.timezone }}）</span>
      <p v-if="w.pickup_state.is_open" class="ok">取货窗开放中，今日 {{ w.pickup_state.closes_local }} 关闭</p>
      <p v-else class="muted">取货窗关闭中，下次开窗：{{ w.pickup_state.next_open_local }}</p>
    </section>

    <p v-if="err" class="err">{{ err }}</p>
    <input v-model="claimer" placeholder="你的名字" />
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <button @click="claim">认领锁定</button>
      <button class="ghost" @click="release">释放</button>
      <button class="ghost" :disabled="fulfillBlocked" @click="fulfill">核销完成</button>
      <span v-if="fulfillBlocked" class="tag">窗外不可核销，{{ w.pickup_state?.next_open_local }} 开窗</span>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
const props = defineProps({ id: String })
const w = ref({})
const claimer = ref('访客')
const err = ref('')
const fulfillBlocked = computed(() =>
  w.value.status === 'claimed' && w.value.pickup_state && !w.value.pickup_state.is_open)
async function load() { w.value = await api('/wishes/' + props.id) }
async function claim() {
  err.value=''; try { await api('/wishes/'+props.id+'/claim',{method:'POST',body:JSON.stringify({claimer:claimer.value})}); await load() } catch(e){ err.value=e.message }
}
async function release() {
  err.value=''; try { await api('/wishes/'+props.id+'/release',{method:'POST',body:'{}'}); await load() } catch(e){ err.value=e.message }
}
async function fulfill() {
  err.value=''; try { await api('/wishes/'+props.id+'/fulfill',{method:'POST',body:'{}'}); await load() }
  catch(e){ err.value=e.message; await load() }
}
onMounted(load)
</script>
<style scoped>
.winbox { background: var(--card); border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
.dot.open { background:#3a7d44; }
.dot.closed { background:var(--muted); }
.ok { color:#3a7d44; margin:6px 0 0; width:100%; }
.muted { color:var(--muted); margin:6px 0 0; width:100%; }
</style>
