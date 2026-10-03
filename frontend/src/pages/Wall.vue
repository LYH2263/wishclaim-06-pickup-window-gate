<template>
  <div class="wall">
    <h1 class="serif">愿望墙</h1>
    <p class="tag">无顶栏 · 瀑布流 · 点卡片认领 · 仅窗内可核销</p>
    <p v-if="err" class="err">{{ err }}</p>
    <div class="masonry">
      <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
        <h3>{{ w.title || '（无标题）' }}</h3>
        <p>{{ w.note }}</p>
        <div class="winline" v-if="w.pickup_state">
          <span :class="['dot', w.pickup_state.is_open ? 'open' : 'closed']"></span>
          <span class="tag">
            <template v-if="w.status==='claimed'">
              {{ w.pickup_state.is_open ? '取货窗开放中 · 今日 ' + w.pickup_state.closes_local + ' 关闭' : '闭窗 · ' + w.pickup_state.next_open_local + ' 开窗' }}
            </template>
            <template v-else>{{ w.pickup_state.human }}</template>
          </span>
        </div>
        <span class="tag">{{ w.status }} · {{ w.data_quality }}</span>
        <button v-if="w.status==='claimed'" class="mini"
                :disabled="!w.pickup_state || !w.pickup_state.is_open"
                @click.stop="fulfill(w)">核销完成</button>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
const err = ref('')
async function load() { rows.value = await api('/wishes') }
async function fulfill(w) {
  err.value = ''
  try { await api('/wishes/'+w.id+'/fulfill', { method:'POST', body:'{}' }); await load() }
  catch (e) { err.value = e.message; await load() }
}
onMounted(load)
</script>
<style scoped>
.winline { display:flex; gap:6px; align-items:center; margin:4px 0; }
.dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
.dot.open { background:#3a7d44; }
.dot.closed { background:var(--muted); }
button.mini { margin-top:10px; padding:5px 12px; font-size:13px; }
button.mini:disabled { opacity:.5; cursor:not-allowed; }
</style>
