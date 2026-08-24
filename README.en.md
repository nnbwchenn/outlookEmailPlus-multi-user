# OutlookMail Plus — Multi-User Edition

> This project is a fork of [ZeroPointSix/outlookEmailPlus](https://github.com/ZeroPointSix/outlookEmailPlus).
> The upstream project is a single-admin mailbox manager; this fork adds **multi-user mode** and an **activation-code distribution system** on top of its full feature set, for scenarios where a mail pool is shared across multiple people. This is the first release of the fork.

A mailbox manager and verification-code extractor built for registration workflows: batch inbox reading, one-click code extraction, mail-pool API, browser extension, push notifications — with multi-user isolation on top.

---

## Relationship to Upstream

| | Upstream | This Fork |
| --- | --- | --- |
| Login | Single password, single admin | Multi-user accounts (admin / member) |
| Mailbox ownership | All owned by the admin | Mailboxes can be assigned to users; data isolated per user |
| Mailbox distribution | — | Activation-code redemption / manual assignment by admin |
| One-click update (Watchtower) | Supported | **Removed** |

All other core capabilities are unchanged from upstream.

## What This Fork Adds

### Multi-User Mode (admin / member)

- On first startup an `admin` account is created automatically (password from `LOGIN_PASSWORD`); admins create member accounts under "User Management"
- **admin**: full functionality + user management + mailbox assignment/recall (the assignment picker lists all mailboxes annotated with their current owner and supports ownership transfer)
- **member**:
  - Sees and operates only their own mailboxes (isolated at the database level via `owner_user_id`, not just hidden in the UI)
  - Overview dashboards and refresh stats cover only their assigned mailboxes
  - Admin surfaces such as pool management and system activity are not visible
  - Can configure their own notification channels
  - External API access is toggled and rate-limited per user
- Permission-hardened via audit: members cannot reach other users' mailboxes or admin endpoints; all critical operations are written to the audit log

### Activation-Code Distribution

- Admins generate codes in batches (1–200 per batch, each binding 1–100 mailboxes), with notes, enable/disable, and delete
- **Anti-overissue quota ledger**: before issuance the system validates that "outstanding quota of unredeemed codes + this batch ≤ currently unassigned mailboxes", so codes that could never be redeemed can't be created; the ledger endpoint `GET /api/admin/activation-codes/summary` reports available mailboxes / outstanding quota / remaining capacity
- A logged-in user redeems a code and the system atomically binds unassigned mailboxes to their account
- Each code can be redeemed exactly once; failed redemptions are throttled (10/min) against brute-force guessing
- A "My Activations" view lists the mailboxes bound via codes

## Core Capabilities (inherited from upstream)

- **Multi-protocol inbox**: Outlook OAuth (Graph / IMAP) + generic IMAP (Gmail, QQ, 163, self-hosted servers)
- **One-click verification-code extraction**: rule extraction + confidence gating + AI fallback; case preservation, hyphenated-code recognition, newest-email selection across folders; frontend button and external API share the same pipeline
- **Mail pool & external API**: `X-API-Key` auth, `project_key`-scoped claiming, success reuse, invalid-token governance (unified `invalid_grant` classification), batch deactivate
- **Browser extension** (Chrome/Edge MV3): claim → auto-extract code/link → complete/release without switching tabs
- **Bulk operations**: batch fetch mail, select-all bulk actions, tag/untag, move group, refresh tokens, delete
- **Notification channels**: Email (SMTP) / Telegram / Webhook side by side
- **Overview dashboard**: Summary / Verification / External API / Mailbox Pool / Activity tabs
- **OAuth Token tool**: get authorization link, exchange and import tokens (Method 1 / Method 2)
- **Also**: bilingual UI (EN/ZH), responsive layout for desktop/tablet/mobile, groups & tags, performance work (bootstrap endpoint + caching)

> Removed relative to upstream: one-click update (Watchtower / Docker API self-update), temp mail.

## Quick Start

### Docker Compose (recommended)

```bash
git clone https://github.com/nnbwchenn/outlookEmailPlus-multi-user.git
cd outlookEmailPlus-multi-user
cp .env.example .env   # if absent, create .env manually
```

Minimum `.env`:

```env
SECRET_KEY=change-me-to-a-long-random-string
LOGIN_PASSWORD=initial-admin-password
```

Start:

```bash
docker compose up -d
```

Default port is `5001` (change via `APP_PORT` in `.env`). Open `http://localhost:5001` and log in as `admin` with your `LOGIN_PASSWORD`.

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

### Local Run

```bash
python -m venv .venv
pip install -r requirements.txt
python web_outlook_app.py
```

### Run Tests

```bash
pytest tests/
```

## Common Environment Variables

| Variable | Description |
| --- | --- |
| `SECRET_KEY` | Required; session security and sensitive-data encryption, must stay stable |
| `LOGIN_PASSWORD` | Initial password; used to create the admin account on first start, then hashed in DB |
| `DATABASE_PATH` | SQLite path, default `data/outlook_accounts.db` |
| `PORT` / `HOST` | Web server bind address |
| `SCHEDULER_AUTOSTART` | Whether background scheduler jobs start automatically |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` / `GUNICORN_TIMEOUT` | Gunicorn concurrency settings |
| `OAUTH_TOOL_ENABLED` | Enable the OAuth token tool, default `true` |
| `OAUTH_CLIENT_ID` / `OAUTH_REDIRECT_URI` | Outlook OAuth app configuration |
| `PROXY_FIX_ENABLED` / `TRUSTED_PROXIES` | ProxyFix middleware and trusted proxy list behind reverse proxies |

## External API and Mail Pool Integration

To connect registration workers or automation platforms, use the controlled external API:

- Path prefix: `/api/external/*`, auth header: `X-API-Key`
- Mail-pool endpoints: `/api/external/pool/*` (claim, fetch code, release, complete)
- Supports multiple keys, per-caller mailbox scoping, public-mode allowlists and rate limits
- Full contract: [Registration Worker and Mail Pool API](./registration-mail-pool-api.en.md) / [Chinese version](./注册与邮箱池接口文档.md)

## Project Layout

```text
outlook_web/          Flask application core (controllers / routes / services / repositories)
templates/            Page templates
static/               Frontend scripts and styles
browser-extension/    Chrome/Edge MV3 browser extension
data/                 SQLite data and runtime files
tests/                Automated tests
docs/                 PRDs / design docs / project map
web_outlook_app.py    Entry point
```

## Acknowledgements

This project is forked from [ZeroPointSix/outlookEmailPlus](https://github.com/ZeroPointSix/outlookEmailPlus) — thanks to the original author. The upstream project drew ideas from [assast/outlookEmail](https://github.com/assast/outlookEmail) and [gblaowang-i/MailAggregator_Pro](https://github.com/gblaowang-i/MailAggregator_Pro), and is built on Flask, SQLite, Microsoft Graph API, IMAP, and APScheduler.

## License

Apache License 2.0
