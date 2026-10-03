# Wishclaim · 礼物愿望认领

发布 → 认领锁定（互斥+TTL）→ 核销/释放。

| 服务 | 端口 |
| --- | --- |
| 前端 | 5200 |
| API | 10200 |

```bash
docker compose up --build
pytest backend/app/tests
```

0-1：`wish_comment` / `secret_santa` / `price_cap`。

取货窗：`app/modules/pickup_window`（判定 check / 快照 snapshot / 投影 projection）。
认领不卡窗、核销卡窗（窗外核销 409 且状态不变）；时刻按 `pickup_timezone` 本地墙钟解释，不按 UTC；
发布落窗快照，改默认窗不回写已发布愿望。
