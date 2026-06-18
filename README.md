<div align="center">

<img src="assets/screenshots/dashboard.png" alt="AI Email Assistant" width="100%"/>

# AI Email Assistant

**Intelligent Gmail automation with a human-in-the-loop safety layer**

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Gmail API](https://img.shields.io/badge/Gmail-OAuth2-EA4335?style=flat-square&logo=gmail&logoColor=white)](https://developers.google.com/gmail/api)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-GPT--4o--mini-412991?style=flat-square&logo=openai&logoColor=white)](https://openrouter.ai)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_API-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)](LICENSE)

Reads, classifies, and summarizes incoming Gmail — then decides whether to auto-reply or route to a human via Telegram. Sensitive content (OTPs, bank alerts) is detected, masked, and never auto-replied. A real-time Streamlit dashboard tracks everything.

[Quick Start](#-quick-start) · [Features](#-features) · [Architecture](#️-architecture) · [Screenshots](#-screenshots) · [Demo](#-demo)

</div>

---

## Demo

<div align="center">
<img src="assets/demo.gif" alt="AI Email Assistant Demo" width="100%"/>

*Gmail fetch → AI classification → Sensitive masking → Telegram approval → Dashboard update*
</div>

---

## Features

### AI Processing Pipeline
- **Classification** — routes each email into IMPORTANT / SPAM / PROMOTION / SOCIAL / UPDATES / SENSITIVE
- **Summarization** — 3-bullet summaries via GPT-4o-mini
- **Priority Scoring** — urgency score 1–10 with action-required detection
- **Reply Generation** — context-aware professional drafts

### Human Decision Guard
The most critical safety layer. Before auto-sending any reply to an IMPORTANT email, a two-layer detector (20+ regex patterns + LLM fallback) checks whether the email requires a personal decision:

| Requires Human | Auto-Reply Allowed |
|---|---|
| "Did you complete the project?" | "Your access request has been approved." |
| "Can you attend tomorrow at 7:30?" | "Here is the meeting link." |
| "Are you interested in joining our team?" | "Your order has been shipped." |
| "What do you think about the proposal?" | Weekly newsletter / digest |

When flagged, a Telegram message is sent with the AI draft and three inline buttons — **✅ Send Draft · ✏️ Edit Reply · ❌ Ignore** — and nothing is sent until you decide.

### Sensitive Email Detection
Two-layer detection (40+ regex patterns + LLM deep scan) covering OTPs, bank alerts, password resets, login alerts, card alerts, fraud alerts, KYC, and legal notices.

- Codes are masked (`482917` → `[CODE MASKED]`) before storage, AI processing, or Telegram
- Category forced to SENSITIVE, priority forced to HIGH
- Auto-reply permanently blocked — Telegram notifies you to open Gmail directly

### Dashboard & Monitoring
- 6 KPI cards: Total · Pending · Approved · Auto-Sent · Sensitive · Ignored
- Plotly charts: category donut, reply-status breakdown, processing timeline
- 7 tabs: Emails · Pending · Sensitive · Replies · Analytics · Detail
- Polls Gmail every 60 seconds automatically

---

## Architecture

```
Gmail Inbox (OAuth2)
        │
        ▼
email_engine/
  fetcher.py   ← Gmail API list() + get()
  parser.py    ← MIME decode, base64url, header extraction
        │
        ▼
ai_processing/
  1. sensitive_detector   ← RUNS FIRST (40+ regex → LLM fallback)
     masks codes, overrides category, blocks reply
  2. summarizer           ← 3-bullet summary
  3. classifier           ← 6 categories + SENSITIVE override
  4. priority_analyzer    ← score 1–10, urgency, action flag
  5. decision_detector    ← RUNS BEFORE REPLY (20+ regex → LLM fallback)
     returns AUTO_REPLY_ALLOWED or HUMAN_DECISION_REQUIRED
  6. reply_generator      ← professional draft
        │
   ┌────┴────┐
   ▼         ▼
AUTO      HUMAN_DECISION_REQUIRED
REPLY       │
  │         ▼
  │    telegram_service.py
  │    → Inline approval buttons
  │    → Email saved as PENDING_APPROVAL
  │
  ▼
drafts/gmail_sender.py
  3 safety gates:
  · category allowlist check
  · email address validation
  · no-reply detection
        │
        ▼
storage/data_store.py → database/db_manager.py (SQLite)
        │
        ▼
dashboard/app.py (Streamlit)
```

---

## Screenshots

<div align="center">

<img src="assets/screenshots/dashboard.png" width="100%"/>
<em>Dashboard — KPI cards, system status, tech stack</em>

<br/><br/>

<img src="assets/screenshots/recent-emails.png" width="100%"/>
<em>Emails tab — category chart and color-coded cards with priority badges</em>

<br/><br/>

<img src="assets/screenshots/sensitive.png" width="100%"/>
<em>Sensitive tab — codes masked, auto-reply blocked</em>

<br/><br/>

<img src="assets/screenshots/pending.png" width="100%"/>
<em>Pending tab — AI draft shown, Telegram action buttons, flagging reason</em>

<br/><br/>

<img src="assets/screenshots/analytics.png" width="100%"/>
<em>Analytics tab — distributions, timeline, full stats grid</em>

<br/><br/>

<img src="assets/screenshots/telegram.jpeg" width="60%"/>
<em>Telegram approval flow — inline buttons for each pending email</em>

</div>

---

## Quick Start

**Prerequisites:** Python 3.13+, a Gmail account, an [OpenRouter API key](https://openrouter.ai/keys), and a Telegram bot (via [@BotFather](https://t.me/BotFather)).

```bash
git clone https://github.com/syeedarshad/ai-email-assistant.git
cd ai-email-assistant

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Gmail API setup:**
1. [Google Cloud Console](https://console.cloud.google.com) → create project → enable Gmail API
2. Credentials → OAuth 2.0 Client ID → Desktop App → download JSON
3. Rename to `credentials.json`, place in project root

**Environment:**
```bash
cp .env.example .env
```

```env
OPENROUTER_API_KEY=sk-or-v1-your-key
TELEGRAM_BOT_TOKEN=1234567890:your-token
TELEGRAM_CHAT_ID=123456789
YOUR_NAME=Your Name
YOUR_ASSISTANT_NAME=AI Assistant
```

**Verify setup:**
```bash
python setup_check.py
```

**Authenticate Gmail (one-time browser flow):**
```bash
python auth/gmail_auth.py
```

---

## Running

```bash
# Single run
python main.py

# Continuous monitoring (production)
python monitor.py                    # Terminal 1
python telegram_callback_handler.py  # Terminal 2

# Dashboard
streamlit run dashboard/app.py       # http://localhost:8501
```

---

## Database Schema

```sql
CREATE TABLE processed_emails (
    id              TEXT PRIMARY KEY,   -- Gmail message ID
    sender          TEXT,
    sender_email    TEXT,
    subject         TEXT,
    summary         TEXT,               -- AI-generated bullets
    category        TEXT,               -- IMPORTANT / SPAM / etc
    sensitive_type  TEXT,               -- OTP / BANK_ALERT / etc
    is_sensitive    INTEGER DEFAULT 0,
    priority        TEXT,               -- "8/10 | HIGH | ACTION: YES"
    reply_draft     TEXT,
    sent_reply      INTEGER DEFAULT 0,
    reply_status    TEXT DEFAULT 'AUTO_SENT',  -- see below
    decision_reason TEXT,
    decision_by     TEXT,               -- "regex" | "llm" | "default"
    processed_at    TEXT                -- ISO 8601
);
```

| `reply_status` | Meaning |
|---|---|
| `AUTO_SENT` | Replied automatically |
| `PENDING_APPROVAL` | Awaiting Telegram decision |
| `APPROVED` | Approved and sent via Telegram |
| `IGNORED` | User chose not to reply |

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `TELEGRAM_BOT_TOKEN` | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | — | Your personal chat ID |
| `MAX_EMAILS_PER_FETCH` | `5` | Emails per cycle |
| `MONITOR_INTERVAL_SECONDS` | `60` | Poll interval |
| `AUTO_REPLY_CATEGORIES` | `IMPORTANT` | Categories eligible for auto-reply |
| `REPLY_TONE` | `professional` | `professional` / `casual` / `brief` |
| `GMAIL_FETCH_QUERY` | `is:unread` | Gmail search filter |

---

## Tests

```bash
pip install pytest pytest-mock
pytest tests/ -v
# 30 passed in ~2.4s
```

Covers: regex OTP/bank detection, code masking, LLM-fallback safe mode, human-decision regex triggers, auto-reply allowlist, and subtle LLM-caught cases.

---

## Security

| Concern | Mitigation |
|---|---|
| Gmail credentials | `credentials.json` + `token.json` in `.gitignore` |
| API keys | Environment variables only |
| OTP / bank codes | Masked before storage, AI calls, or Telegram |
| Auto-reply safety | 3 gates: category · email validation · no-reply detection |
| Personal decisions | Human Decision Layer blocks all commitment-related replies |

The AI will **never** automatically claim you completed a task, accept a meeting invite, confirm attendance, state your availability, share your opinion, or make a commitment on your behalf.

---

## Roadmap

- [ ] Gmail Push Notifications via Pub/Sub (replace polling)
- [ ] Email thread context for smarter reply continuity
- [ ] Parallel AI processing (3× faster per email)
- [ ] Daily Telegram digest report
- [ ] PostgreSQL migration for multi-user support
- [ ] Docker + Railway/Render deployment
- [ ] Web-based approval interface (alternative to Telegram)

---

## What This Demonstrates

| Area | Implementation |
|---|---|
| AI System Design | Modular LLM pipeline with 6 specialized processors |
| Human-in-the-Loop Safety | Two-layer decision detection preventing unauthorized AI actions |
| OAuth2 Integration | Gmail token lifecycle with silent auto-refresh |
| Secure Data Handling | Code masking, zero raw-code storage |
| Workflow Orchestration | Multi-step approval across Telegram + Gmail + SQLite |
| Production Architecture | Repository pattern, rotating logs, migration-ready DB schema |

---

## Project Structure

```
ai-email-assistant/
├── ai_processing/
│   ├── sensitive_detector.py   # 40+ regex + LLM fallback
│   ├── decision_detector.py    # 20+ regex + LLM safety check
│   ├── summarizer.py
│   ├── classifier.py
│   ├── priority_analyzer.py
│   └── reply_generator.py
├── auth/gmail_auth.py          # OAuth2 token lifecycle
├── email_engine/
│   ├── fetcher.py              # Gmail API list + get
│   └── parser.py               # MIME decode, headers
├── drafts/
│   ├── gmail_sender.py         # safe_send_reply() with 3 gates
│   └── gmail_draft_creator.py
├── database/db_manager.py      # SQLite CRUD + reply_status tracking
├── storage/data_store.py       # Repository abstraction
├── notifications/telegram_service.py
├── dashboard/app.py            # Streamlit dark dashboard
├── utils/logger.py             # Rotating file + console logger
├── tests/
│   ├── test_sensitive_detector.py  # 14 tests
│   └── test_decision_detector.py   # 16 tests
├── main.py
├── monitor.py
├── telegram_callback_handler.py
└── setup_check.py
```

---

## License

MIT © 2025 [Arshad](https://github.com/syeedarshad)
---

<div align="center">

Built with Python · OpenRouter · Gmail API · Telegram Bot API · Streamlit · SQLite

</div>