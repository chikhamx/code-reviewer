# Code Review Agent — 飞书真实环境部署指南

## 架构概览

```
用户 @bot 在飞书群发消息
       │
       ▼
飞书服务器 ──WebSocket 长连接──→  FastAPI (本机 :8000)
       │                                    │
       │  lark-oapi SDK              IMGateway.handle_message()
       │  (FeishuWSListener)                   │
       │                            ┌──────────┼──────────┐
       │                            ▼          ▼          ▼
       │                      Normalizer  IntentRouter  Conversation
       │                      (消息格式化)  (意图识别)    (会话管理)
       │                            │
       │                            ▼
       │                      ActionDispatcher
       │                            │
       │                ┌───────────┼───────────┐
       │                ▼           ▼           ▼
       │           ReviewPR   Explain/Refactor  Chat
       │                │           │           │
       │                ▼           ▼           ▼
       │          Orchestrator   LLM Router   LLM Router
       │          (审查引擎)      (模型调用)    (模型调用)
       │                │
       │                ▼
       │    ┌───────────────────────┐
       │    │ PlatformCommenter     │──→ GitHub PR Comment
       │    │ WebhookDispatcher     │──→ 飞书群/钉钉/Slack 推送
       │    └───────────────────────┘
       │
       ◄── FeishuSDKClient.send_message() ──  Agent 回复消息
```

**核心优势**：使用 `lark-oapi` SDK 的 WebSocket 长连接，**无需 ngrok、无需公网 URL、无需配置事件订阅请求网址**。

---

## 第一步：环境准备

```bash
# 1. 确认 Python 版本 >= 3.11
python --version

# 2. 进入项目目录
cd D:/chikham/code-review-agent

# 3. 安装依赖（包含 lark-oapi SDK）
pip install -e ".[dev]"

# 4. 确认安装成功
python -c "from code_review_agent.bootstrap import bootstrap; print('OK')"
python -c "from lark_oapi.ws import Client; print('lark-oapi OK')"
```

---

## 第二步：配置 LLM Provider（至少一个）

```bash
cp config/llm.example.yaml config/llm.yaml
```

编辑 `config/llm.yaml`，**最少启用一个 Provider**。推荐用 DeepSeek（最便宜）或 Claude：

```yaml
providers:
  deepseek:
    enabled: true
    api_key: "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    base_url: "https://api.deepseek.com/v1"
    models:
      - id: deepseek-v3
        alias: [smart, default]
        max_tokens: 8192
      - id: deepseek-chat
        alias: [fast]
        max_tokens: 4096
```

> API Key 获取：DeepSeek 官网 → API Keys → 创建，新用户有免费额度。

验证 LLM 连通性（启动服务后）：

```bash
curl -X POST http://localhost:8000/api/llm/test \
  -H "Content-Type: application/json" \
  -d '{"provider":"deepseek","model":"deepseek-v3","prompt":"hello"}'
```

---

## 第三步：创建飞书应用

### 3.1 进入飞书开放平台

打开 https://open.feishu.cn → 登录 → 进入「开发者后台」

### 3.2 创建企业自建应用

1. 点击「创建企业自建应用」
2. 填写：
   - **应用名称**：`Code Review Bot`
   - **应用描述**：`AI code review agent`
3. 创建后进入应用详情页

### 3.3 添加应用能力

左侧菜单 → **添加应用能力** → 勾选 **「机器人」** → 保存

### 3.4 配置机器人

左侧菜单 → **机器人** → 配置：

- **消息模式**：选择 **HTTP 模式**（WebSocket 长连接通过 lark-oapi SDK 自动管理）
- **消息卡片请求网址**：不需要填写

### 3.5 事件订阅（可选，仅 HTTP 模式 fallback 时需要）

> **使用 WebSocket 长连接时不需要配置事件订阅请求网址。**
> 如果你也想保留 HTTP 回调作为备选方案，可以按传统方式配置。

### 3.6 配置权限

左侧菜单 → **权限管理** → 搜索并开通：

| 权限 | 说明 | 用途 |
|------|------|------|
| `im:message` | 获取用户发送给机器人的消息 | 接收消息 |
| `im:message:send_by_bot` | 以机器人的身份发消息 | 回复消息 |
| `im:chat` | 获取群聊信息 | 获取群 ID |

全部设置为**「全员可用」**（如果你的应用范围选的是全员）。

### 3.7 获取凭证

左侧菜单 → **凭证与基础信息** → 记录以下值：

```
App ID:       cli_xxxxxxxxxxxxxxxx
App Secret:   xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3.8 发布应用

**重要：必须先发布应用，WebSocket 连接才能接收消息。**

右上角 → **「创建版本」** → 填写版本号（如 `1.0.0`）→ **「保存」** → **「申请发布」**

如果你的账号是管理员，会自动审批通过。如果是普通成员，需要找管理员审批。

---

## 第四步：配置 Agent

### 4.1 创建 IM 配置文件

```bash
cp config/im.example.yaml config/im.yaml
```

### 4.2 编辑 `config/im.yaml`

```yaml
platforms:
  feishu:
    enabled: true
    app_id: "cli_xxxxxxxxxxxxxxxx"        # 飞书后台的 App ID
    app_secret: "xxxxxxxxxxxxxxxxxxxxxx"  # 飞书后台的 App Secret
    bot_name: "Code Review Bot"
    use_websocket: true                   # 使用 WebSocket 长连接（无需 ngrok）
```

`use_websocket: true` 表示使用 lark-oapi SDK 的 WebSocket 长连接接收事件。设为 `false` 则回退到 HTTP webhook 模式。

### 4.3 配置 GitHub Token（需要 Review PR 功能时）

编辑 `config/default.yaml` 或设环境变量：

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

> 获取方式：GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
> 权限：`Contents: Read-only`, `Pull requests: Read & Write`

---

## 第五步：启动服务

```bash
# 开发模式（推荐，有日志）
uvicorn code_review_agent.api.app:app --host 0.0.0.0 --port 8000 --log-level info
```

看到以下日志表示启动成功：

```
INFO: Configuration loaded from config
INFO: LLM providers: ['deepseek']
INFO: Feishu SDK client initialized
INFO: IM gateway initialized
INFO: Feishu WS listener created
INFO: Bootstrap complete — all components initialized
INFO: Feishu WebSocket listener started in background thread
INFO: Feishu WS listener starting (app_id=cli_xxxx)
INFO: Code Review Agent ready
```

**不需要 ngrok，不需要公网 URL**。WebSocket 长连接由 Agent 主动发起，连接飞书服务器后即可接收消息。

---

## 第六步：添加机器人到群

1. 飞书客户端 → 创建一个测试群
2. 群设置 → **群机器人** → **添加机器人** → 搜索 `Code Review Bot` → 添加
3. 看到提示「机器人 Code Review Bot 加入群聊」

---

## 第七步：测试验证

### 7.1 基础对话测试

在群里 @机器人：

```
@Code Review Bot help
```

Agent 回复：

```
I'm a code review assistant. Here's what I can do:
- review https://github.com/org/repo/pull/42 — Review a PR
- explain <code> — Explain code logic
- suggest fix for <issue> — Get fix suggestions
- refactor <code> — Get refactoring advice
- help — Show this menu
```

### 7.2 PR Review 测试

在群里 @机器人：

```
@Code Review Bot review https://github.com/yourorg/yourrepo/pull/1
```

完整流程日志：

```
INFO: Feishu WS event received: msg_id=om_xxxx chat_id=oc_xxxx
INFO: IM gateway processing feishu message
INFO: L1 classified: review .../pull/1 -> review_pr (score=10)
INFO: GitHub: fetched PR #1 in yourorg/yourrepo
INFO: LLM review: 8000 tokens, 3 findings
INFO: Review complete: PR #1, 8 findings, 4500ms
INFO: Feishu reply sent: msg_id=om_xxxx chat_id=oc_xxxx
```

Agent 回复：

```
## Code Review: Add user login feature
**Risk**: 🔴 HIGH
**Findings**: 8 issues

- [CRITICAL] `auth.py:42` — Plain-text password comparison
- [ERROR] `auth.py:45` — SQL injection via string formatting
- [WARNING] `login.ts:32` — Error message leaks stack trace
...

**Summary**: The PR introduces 2 critical security issues that must be fixed...

Need suggestions for a specific issue? Reply with "how to fix #1"
```

### 7.3 连续对话 / 追问测试

```
@Code Review Bot 第1个问题怎么修？
```

Agent 根据会话上下文，知道你在问上一个 Review 的第一个 finding，回复修复方案。

---

## 故障排查

| 现象 | 排查 |
|------|------|
| WebSocket 连接失败 | 检查 app_id/app_secret 是否正确；确认应用已发布 |
| 发了消息没反应 | 查看 Agent 日志中 WS 连接状态；确认 app 已发布 |
| 回复内容为空 | 检查 LLM API Key 是否正确；`curl /api/llm/test` 测试 |
| LLM 调用超时 | DeepSeek/Claude API 可能超时 30s，但 WebSocket 模式下无 3s 限制，LLM 调用完成后通过 SDK 发送消息 |
| SDK 报错 | 检查 `lark-oapi` 版本：`pip show lark-oapi`（需要 >= 1.6.0） |

---

## HTTP Webhook 模式（备选）

如果需要使用传统 HTTP 回调模式（例如部署在公网服务器上），将 `config/im.yaml` 中：

```yaml
platforms:
  feishu:
    use_websocket: false   # 关闭 WebSocket，使用 HTTP 回调
```

然后在飞书开放平台 → 事件订阅 → 请求网址填入：

```
https://your-domain.com/api/im/feishu
```

此模式下，签名验证、URL 验证等流程与之前相同，由 `api/webhook_im.py` 处理。

---

## 生产部署建议

### 方案 1：直接部署（推荐）

WebSocket 模式下无需公网 URL，Agent 可直接部署在任何能访问飞书 API 的服务器上：

```bash
uvicorn code_review_agent.api.app:app --host 0.0.0.0 --port 8000
```

### 方案 2：Docker 部署

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 方案 3：HTTP 回调模式（需要公网）

```bash
# Nginx 反向代理
server {
    listen 443 ssl;
    server_name bot.yourcompany.com;

    location /api/im/feishu {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```
