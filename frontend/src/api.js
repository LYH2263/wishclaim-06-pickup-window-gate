export async function api(path, opts = {}) {
  const r = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  if (!r.ok) {
    let detail = r.statusText
    try { const j = await r.json(); detail = j.detail || JSON.stringify(j) } catch {}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (r.status === 204) return null
  return r.json()
}

// 取货窗错误码 → 中文提示（与规则页文案同口径）
export const ERR_ZH = {
  end_not_after_start: '结束时间必须晚于开始时间',
  empty_days: '至少选择一个星期',
  bad_days: '星期取值应为 0–6',
  bad_time_format: '时间格式应为 HH:MM',
  bad_timezone: '时区无效（应为 IANA 时区，如 Asia/Shanghai）',
  outside_pickup_window: '当前不在取货时间窗内，状态未变，可等窗内再核销',
}
export function zhErr(e) { return ERR_ZH[e.message] || e.message }
