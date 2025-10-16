# Contextual（中文文档）

> **AI 驱动的研发上下文管家**  
> 常驻钉钉 / Slack / Teams，在开发流程中把 **代码改动** 与 **业务需求** 自动关联。

## 我们解决的问题
- **新人慢**：入职工程师难以理解代码背后的“为什么”
- **维护痛**：定位问题要翻旧单、问同事
- **评审难**：缺少变更背后的业务上下文

## 工作原理
1. **Analyze**：监听 Git 仓库的 `push`
2. **Understand**：LLM 解析 `diff` + `commit message`
3. **Recommend**：查询 Jira，给出**单条最相关任务**
4. **Interact**：在聊天工具里弹出卡片：“可能是 JIRA-123？”
5. **Link**：一键 `[✅ Yes, link it]` 建立永久可查询链接；系统基于反馈持续学习

## 架构（Phase 2 MVP）
- **webhook**（:8001）接收 Git Webhook，校验签名，入 MQ（`git_commit_raw`）
- **core**（:8000）消费事件 →（MVP）给出示例推荐 → 发送钉钉卡片 → 记录通知
- **callback**（:8003）接收卡片点击 → 记录 `interaction_log`
- **数据库**：PostgreSQL + `pgvector`（后续可迁专用向量库）
- **消息队列**：RabbitMQ，解耦削峰

## 快速开始
1. 复制环境变量
   ```bash
   cp .env.example .env
   # 填写 DINGTALK_WEBHOOK_URL / DINGTALK_SECRET（加签）/ DINGTALK_KEYWORD / PUBLIC_BASE_URL / GIT_WEBHOOK_SECRET
    ```

2. 启动服务

   ```bash
   docker compose up -d
   ```
3. 暴露回调（指向 8003）

   ```bash
   cloudflared tunnel --url http://localhost:8003
   make set-callback NEW=https://<你的-trycloudflare-域名>
   ```
4. 配置 GitHub Webhook（指向 8001）

   * Payload URL: `https://<你的-trycloudflare-域名>/ingest/git`
   * Content type: `application/json`
   * Secret: 与 `.env` 中 `GIT_WEBHOOK_SECRET` 一致
5. 一键冒烟

   ```bash
   make smoke
   # 预期：健康检查 OK；群里收到“smoke-check”文本；出现 ActionCard
   ```

## 常见问题

* **卡片没出现但 DB 有 delivered_at**：多数是钉钉机器人启用了**关键词**。确保 `.env` 的 `DINGTALK_KEYWORD` 与机器人设置一致（本项目已自动把关键词前缀到消息）
* **GitHub Webhook 404**：确认路径为 `/ingest/git`
* **回调打不开**：更新 `PUBLIC_BASE_URL` 后需**发送新卡片**，旧卡片仍指向旧域名

更多运维见 `docs/RUNBOOK.md`。
