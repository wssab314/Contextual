# ===== Contextual Makefile =====
SHELL := /bin/bash

# 默认端口
WEBHOOK_PORT ?= 8001
CALLBACK_PORT ?= 8003

.PHONY: up down rebuild-core restart-core logs-core logs-webhook logs-callback smoke set-callback env mq db-last

up:
	docker compose up -d

down:
	docker compose down

rebuild-core:
	docker compose build core && docker compose up -d core

restart-core:
	docker compose up -d --force-recreate core

logs-core:
	docker compose logs -f core

logs-webhook:
	docker compose logs -f webhook

logs-callback:
	docker compose logs -f callback

# 一键冒烟测试（健康检查 + 发文本到钉钉 + 模拟 push）
smoke:
	./scripts/smoke.sh

# 更新 PUBLIC_BASE_URL 并让 core 生效：用法 make set-callback NEW=https://xxx.trycloudflare.com
set-callback:
	@if [ -z "$(NEW)" ]; then echo "[ERR] 用法: make set-callback NEW=https://xxx.trycloudflare.com"; exit 2; fi
	@sed -i '' "s#^PUBLIC_BASE_URL=.*#PUBLIC_BASE_URL=$(NEW)#" .env
	@echo "[OK] PUBLIC_BASE_URL -> $(NEW)"
	docker compose up -d --force-recreate core
	docker compose exec -T core env | grep '^PUBLIC_BASE_URL='

# 快速查看关键环境变量
env:
	@grep -E '^(DINGTALK_|PUBLIC_BASE_URL|GIT_WEBHOOK_SECRET|RELAY_URL)=' .env || true

# RabbitMQ 队列概览
mq:
	docker compose exec -T rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers

# 最近入库记录（便于确认闭环）
db-last:
	docker compose exec -T postgres psql -U postgres -d contextual -c "SELECT id, trace_id, commit_hash, delivered_at, clicked_at FROM notifications ORDER BY id DESC LIMIT 5;"
	docker compose exec -T postgres psql -U postgres -d contextual -c "SELECT id, commit_hash, recommended_jira_key, user_feedback, interaction_timestamp FROM interaction_log ORDER BY id DESC LIMIT 5;"
