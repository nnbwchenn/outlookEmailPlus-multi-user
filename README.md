# OutlookMail Plus — 多用户版

> 本项目是 [ZeroPointSix/outlookEmailPlus](https://github.com/ZeroPointSix/outlookEmailPlus) 的 Fork。
> 原版是单管理员的邮箱管理器；本 Fork 在其完整能力之上，新增了 **多用户模式** 与 **激活码分发体系**，适合把邮箱池分给多人使用的场景。当前为 Fork 的首个版本。

一个面向注册流程的 Outlook / IMAP 邮箱管理与验证码提取工具：批量收件、一键取码、邮箱池 API、浏览器扩展、通知推送 —— 并支持多用户隔离使用。

---

## 与原版的关系

| | 原版 | 本 Fork |
| --- | --- | --- |
| 登录 | 单密码，单管理员 | 多用户账号体系（admin / member） |
| 邮箱归属 | 全部属于管理员 | 邮箱可分配给用户，数据按用户隔离 |
| 邮箱分发 | — | 激活码兑换 / 管理员手动分配 |
| 一键更新（Watchtower） | 支持 | **已移除** |

其余核心能力与原版保持一致。

## 本 Fork 新增

### 多用户模式（admin / member）

- 首次启动自动创建管理员账号 `admin`（密码沿用 `LOGIN_PASSWORD`），管理员可在「用户管理」中创建 member 账号
- **admin**：全部功能 + 用户管理 + 邮箱分配/回收（分配选择器列出全部邮箱并标注当前归属，支持转移归属）
- **member**：
  - 仅能看到并操作自己名下的邮箱（数据库层 `owner_user_id` 隔离，非前端遮罩）
  - 数据概览、刷新统计均只统计被分配的邮箱
  - 邮箱池管理、系统活动等管理功能不可见
  - 可自行配置通知渠道
  - 对外 API 按用户独立开关与限速
- 权限经审计加固：member 无法越权访问他人邮箱与管理接口；所有关键操作写入审计日志

### 激活码分发

- 管理员批量生成激活码（每批 1–200 个，每个激活码可绑定 1–100 个邮箱），支持备注、启用/停用、删除
- **防超开额度台账**：签发前校验「未兑换激活码占用额度 + 本次签发 ≤ 当前未分配邮箱数」，杜绝开出无法兑付的空码；额度台账接口 `GET /api/admin/activation-codes/summary` 同步展示可用邮箱数 / 已占额度 / 剩余可签发名额
- 用户登录后输入激活码即可完成兑换：系统原子地把未分配邮箱绑定到该用户名下
- 一个激活码只能被兑换一次；兑换失败限速（每分钟 10 次），防暴力猜码
- 「我的激活」页面可查看自己经激活码绑定的邮箱

## 继承自原版的核心能力

- **多协议收信**：Outlook OAuth（Graph / IMAP）+ 通用 IMAP（Gmail、QQ、163、自建服务器）
- **验证码一键提取**：规则提取 + 置信度门控 + AI 兜底；大小写保真、连字符验证码识别、跨文件夹选取最新验证邮件；对外 API 与前端按钮共用同一提取管线
- **邮箱池与对外 API**：`X-API-Key` 认证，`project_key` 项目隔离申领，成功复用、失效治理（`invalid_grant` 统一判定）、批量置 inactive
- **浏览器扩展**（Chrome/Edge MV3）：一键申领 → 自动提取验证码/链接 → 完成/释放，无需切换标签页
- **批量操作**：批量拉取邮件、全选批量选择、打标签、移动分组、刷新 Token、删除
- **通知渠道**：邮件（SMTP）/ Telegram / Webhook 三通道并存
- **数据概览大盘**：总览 / 验证码提取 / 对外 API / 邮箱池 / 系统活动
- **OAuth Token 工具**：获取授权链接、换取并导入 Token（方式一 / 方式二）
- **其他**：中英双语界面、PC/平板/手机三端自适应、分组与标签、性能优化（bootstrap 端点 + 缓存）

> 相对原版移除：一键更新（Watchtower / Docker API 自更新）、临时邮箱。

## 快速开始

### Docker Compose（推荐）

```bash
git clone https://github.com/nnbwchenn/outlookEmailPlus-multi-user.git
cd outlookEmailPlus-multi-user
cp .env.example .env   # 如无示例文件，手动创建 .env
```

`.env` 最少需要：

```env
SECRET_KEY=请改成随机长字符串
LOGIN_PASSWORD=管理员初始密码
```

启动：

```bash
docker compose up -d
```

默认端口 `5001`（可用 `.env` 中 `APP_PORT` 修改）。访问 `http://localhost:5001`，用 `admin` + `LOGIN_PASSWORD` 登录。

### docker run

```bash
docker build -t outlook-email-plus:multi-user .
docker run -d \
  --name outlook-email-plus \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY=your-secret-key \
  -e LOGIN_PASSWORD=your-admin-password \
  outlook-email-plus:multi-user
```

### 本地运行

```bash
python -m venv .venv
pip install -r requirements.txt
python web_outlook_app.py
```

### 运行测试

```bash
pytest tests/
```

## 常用环境变量

| 变量 | 说明 |
| --- | --- |
| `SECRET_KEY` | 必填，会话安全与敏感数据加密，必须稳定不变 |
| `LOGIN_PASSWORD` | 初始登录密码；首次启动后创建 admin 使用，之后哈希存库 |
| `DATABASE_PATH` | SQLite 路径，默认 `data/outlook_accounts.db` |
| `PORT` / `HOST` | Web 服务监听地址 |
| `SCHEDULER_AUTOSTART` | 后台调度任务是否自动启动 |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` / `GUNICORN_TIMEOUT` | Gunicorn 并发配置 |
| `OAUTH_TOOL_ENABLED` | 是否启用 OAuth Token 工具，默认 `true` |
| `OAUTH_CLIENT_ID` / `OAUTH_REDIRECT_URI` | Outlook OAuth 应用配置 |
| `PROXY_FIX_ENABLED` / `TRUSTED_PROXIES` | 反向代理场景下启用 ProxyFix 与可信代理列表 |

## 外部 API 与邮箱池集成

对接注册 worker / 自动化平台请使用受控外部 API：

- 路径前缀：`/api/external/*`，认证头：`X-API-Key`
- 邮箱池端点：`/api/external/pool/*`（申领、取码、释放、完成）
- 支持多 Key、按调用方限制邮箱范围、公网模式白名单与限速
- 详细契约见 [注册与邮箱池接口文档](./注册与邮箱池接口文档.md) / [English version](./registration-mail-pool-api.en.md)

## 项目结构

```text
outlook_web/          Flask 应用主体（controllers / routes / services / repositories）
templates/            页面模板
static/               前端脚本与样式
browser-extension/    Chrome/Edge MV3 浏览器扩展
data/                 SQLite 数据与运行时文件
tests/                自动化测试
docs/                 PRD / 设计文档 / 项目地图
web_outlook_app.py    启动入口
```

## 致谢

本项目 Fork 自 [ZeroPointSix/outlookEmailPlus](https://github.com/ZeroPointSix/outlookEmailPlus)，感谢原作者的工作。原版亦参考了 [assast/outlookEmail](https://github.com/assast/outlookEmail) 与 [gblaowang-i/MailAggregator_Pro](https://github.com/gblaowang-i/MailAggregator_Pro) 的思路，构建于 Flask、SQLite、Microsoft Graph API、IMAP、APScheduler 之上。

## 许可证

Apache License 2.0
