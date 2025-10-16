# Contextual 运行手册（极简）

## 日常启动
- `make up` -> 启动所有服务
- 钉钉、GitHub Webhook 已配好的情况下，正常使用即可

## 网络/隧道变更后自检
1. cloudflared(8003) 启新域名 -> `make set-callback NEW=https://<新域名>`
2. 运行冒烟：`make smoke` 
   - 预期：健康检查OK；钉钉收到 "smoke-check" 文本；群里出现一张新卡片
3. 点卡片 ✅ 后：`make db-last` 
   - 预期：`notifications.clicked_at` 有时间戳；`interaction_log` 新增一行

## GitHub Webhook 域名变更
- 若 cloudflared(8001) 也重启，GitHub 仓库 → Settings → Webhooks → Payload URL 改为  
  `https://<新域名>/ingest/git`  
- Secret 必须与 `.env` 里的 `GIT_WEBHOOK_SECRET` 一致

## 常见问题快速定位
- **卡片没到群里**：先 `make smoke`；若文本消息能到、卡片到不了，多为钉钉机器人**关键词未包含**。确保 `.env` 里有：
  - `DINGTALK_KEYWORD=<与你群里设置一致>`
  - Core 已前缀该关键词（当前代码已内置）
- **队列有 unacked**：多数是 DB 写入失败。看 `make logs-core`，我们已改为“先 ack 再入库”，失败只会告警，不会卡住。
- **回调打不开**：多数是 `PUBLIC_BASE_URL` 还是旧域名。执行  
  `make set-callback NEW=https://<新域名>` 即可。
- **GitHub Webhook 404**：Payload URL 忘了带路径，应为 `/ingest/git`。

## 安全与版本控制
- `.env` 不进仓库（`.gitignore` 已添加）
- `.env.example` 展示变量清单（不含敏感值）
- 任何改动都可用 `git commit` 标记

