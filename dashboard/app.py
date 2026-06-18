# dashboard/app.py — Premium SaaS redesign (v3, render-safe)
# All dynamic HTML built in Python loops replaced with native Streamlit components.
# Static HTML blocks (hero, KPI cards, banners) kept as-is — these render fine.

import os
import sqlite3
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Email Assistant",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#0d1117; color:#e6edf3; }
[data-testid="stHeader"]           { background:transparent; }
.main .block-container             { padding:1.5rem 2rem 2rem; max-width:1400px; }

/* Hero */
.hero-wrap {
    background:linear-gradient(135deg,#161b22 0%,#1a2332 50%,#161b22 100%);
    border:1px solid #30363d; border-radius:16px;
    padding:2rem 2.5rem 1.8rem; margin-bottom:1.8rem;
    position:relative; overflow:hidden;
}
.hero-wrap::before {
    content:""; position:absolute; top:-60px; right:-60px;
    width:220px; height:220px;
    background:radial-gradient(circle,rgba(88,166,255,0.08) 0%,transparent 70%);
    border-radius:50%;
}
.hero-title { font-size:2rem; font-weight:700; color:#e6edf3; margin:0 0 0.3rem; letter-spacing:-0.5px; }
.hero-title span { color:#58a6ff; }
.hero-sub   { font-size:0.9rem; color:#7d8590; margin:0 0 1rem; letter-spacing:0.5px; }
.status-dot {
    display:inline-flex; align-items:center; gap:6px;
    background:rgba(35,134,54,0.15); border:1px solid rgba(35,134,54,0.4);
    border-radius:20px; padding:4px 12px;
    font-size:0.78rem; color:#3fb950; font-weight:500;
}
.status-dot::before {
    content:""; width:7px; height:7px; background:#3fb950;
    border-radius:50%; animation:pulse-g 2s infinite;
}
@keyframes pulse-g { 0%,100%{opacity:1} 50%{opacity:0.4} }
.tech-pills { display:flex; gap:8px; flex-wrap:wrap; margin-top:1rem; }
.tech-pill  {
    background:#21262d; border:1px solid #30363d; border-radius:6px;
    padding:3px 10px; font-size:0.75rem; color:#8b949e;
}

/* KPI cards */
.kpi-card {
    background:#161b22; border:1px solid #30363d; border-radius:14px;
    padding:1.3rem 1.4rem; position:relative; overflow:hidden;
    transition:border-color .2s, transform .15s; height:100%;
}
.kpi-card:hover { border-color:#58a6ff; transform:translateY(-2px); }
.kpi-card::after {
    content:""; position:absolute; bottom:0; left:0; right:0;
    height:3px; border-radius:0 0 14px 14px;
}
.kpi-blue::after   { background:linear-gradient(90deg,#58a6ff,#1f6feb); }
.kpi-red::after    { background:linear-gradient(90deg,#f85149,#da3633); }
.kpi-orange::after { background:linear-gradient(90deg,#e3b341,#d29922); }
.kpi-green::after  { background:linear-gradient(90deg,#3fb950,#238636); }
.kpi-icon  { font-size:1.4rem; margin-bottom:0.6rem; display:block; }
.kpi-value { font-size:2.2rem; font-weight:700; color:#e6edf3; line-height:1; margin-bottom:0.3rem; }
.kpi-label { font-size:0.8rem; color:#7d8590; font-weight:500; text-transform:uppercase; letter-spacing:0.6px; }
.kpi-note  { font-size:0.75rem; margin-top:0.4rem; }
.note-warn { color:#e3b341; }
.note-ok   { color:#3fb950; }

/* Section title */
.sec-title {
    font-size:1rem; font-weight:600; color:#e6edf3;
    margin:0 0 1rem; padding-bottom:0.6rem;
    border-bottom:1px solid #21262d;
}

/* Pipeline step card */
.pipe-card {
    background:#161b22; border:1px solid #30363d; border-radius:12px;
    padding:0.9rem 0.7rem; text-align:center; height:100%;
    border-top:2px solid #58a6ff;
}
.pipe-icon-big { font-size:1.6rem; margin-bottom:6px; }
.pipe-lbl  { font-size:0.75rem; color:#8b949e; font-weight:500; line-height:1.3; }
.pipe-cnt  { font-size:0.85rem; color:#58a6ff; font-weight:700; margin-top:4px; }

/* Email card */
.email-card {
    background:#161b22; border:1px solid #30363d; border-radius:12px;
    padding:0.9rem 1.1rem; margin-bottom:8px; transition:border-color .2s;
}
.email-card:hover { border-color:#58a6ff; }
.email-card.sens  { border-left:3px solid #f85149; }
.email-subj       { font-size:0.9rem; font-weight:600; color:#e6edf3; margin-bottom:5px; }
.email-meta-row   { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.email-sender     { font-size:0.78rem; color:#58a6ff; }
.email-time       { font-size:0.78rem; color:#484f58; }

/* Badges */
.badge {
    display:inline-block; font-size:0.68rem; font-weight:600;
    padding:2px 8px; border-radius:4px; letter-spacing:0.4px; white-space:nowrap;
}
.b-IMPORTANT  { background:rgba(248,81,73,.15);  color:#f85149; border:1px solid rgba(248,81,73,.3);   }
.b-SPAM       { background:rgba(139,148,158,.1); color:#8b949e; border:1px solid rgba(139,148,158,.25);}
.b-PROMOTION  { background:rgba(227,179,65,.1);  color:#e3b341; border:1px solid rgba(227,179,65,.25); }
.b-SOCIAL     { background:rgba(63,185,80,.1);   color:#3fb950; border:1px solid rgba(63,185,80,.25);  }
.b-UPDATES    { background:rgba(88,166,255,.1);  color:#58a6ff; border:1px solid rgba(88,166,255,.25); }
.b-SENSITIVE  { background:rgba(248,81,73,.2);   color:#ff7b72; border:1px solid rgba(248,81,73,.5);   }
.b-priority   { background:rgba(88,166,255,.08); color:#79c0ff; border:1px solid rgba(88,166,255,.2);  font-size:0.65rem; }
.b-replied    { background:rgba(63,185,80,.1);   color:#3fb950; border:1px solid rgba(63,185,80,.25);  }
/* Human Decision Layer badges */
.b-AUTO_SENT         { background:rgba(63,185,80,.1);   color:#3fb950; border:1px solid rgba(63,185,80,.25);  }
.b-PENDING_APPROVAL  { background:rgba(227,179,65,.15); color:#e3b341; border:1px solid rgba(227,179,65,.4);  }
.b-APPROVED          { background:rgba(63,185,80,.1);   color:#3fb950; border:1px solid rgba(63,185,80,.25);  }
.b-IGNORED           { background:rgba(139,148,158,.1); color:#8b949e; border:1px solid rgba(139,148,158,.25);}
/* Pending approval card */
.pending-card {
    background:#161b22; border:1px solid rgba(227,179,65,.35); border-left:3px solid #e3b341;
    border-radius:12px; padding:0.9rem 1.1rem; margin-bottom:8px;
    transition:border-color .2s;
}
.pending-card:hover { border-color:#e3b341; }
.pending-draft {
    font-size:0.8rem; color:#7d8590; background:#0d1117;
    border:1px solid #21262d; border-radius:8px;
    padding:0.6rem 0.9rem; margin-top:6px;
    white-space:pre-wrap; line-height:1.5;
}

/* Reply card */
.reply-card    { background:#161b22; border:1px solid #30363d; border-radius:12px; overflow:hidden; margin-bottom:14px; }
.reply-hdr     { background:#21262d; padding:0.8rem 1.2rem; border-bottom:1px solid #30363d; }
.reply-subj    { font-size:0.85rem; font-weight:600; color:#e6edf3; }
.reply-to      { font-size:0.75rem; color:#58a6ff; margin-top:2px; }
.reply-body-w  { padding:1rem 1.2rem; }
.reply-lbl     { font-size:0.7rem; font-weight:600; color:#484f58; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }
.reply-txt     {
    font-size:0.82rem; color:#8b949e; line-height:1.6;
    background:#0d1117; border:1px solid #21262d; border-radius:8px;
    padding:0.8rem 1rem; white-space:pre-wrap;
}

/* Sensitive banner */
.sens-banner {
    background:rgba(248,81,73,.08); border:1px solid rgba(248,81,73,.3);
    border-radius:10px; padding:1rem 1.2rem; margin-bottom:1.2rem;
    font-size:0.85rem; color:#ff7b72; font-weight:500;
}

/* Empty state */
.empty-state { text-align:center; padding:3rem 2rem; color:#484f58; }
.empty-icon  { font-size:3rem; margin-bottom:1rem; }
.empty-title { font-size:1.1rem; color:#7d8590; font-weight:600; margin-bottom:0.5rem; }
.empty-sub   { font-size:0.85rem; }

/* Tabs */
[data-testid="stTabs"] [role="tablist"] {
    background:#161b22; border-radius:10px; padding:4px;
    border:1px solid #30363d; gap:2px;
}
[data-testid="stTabs"] button[role="tab"] {
    border-radius:7px !important; color:#7d8590 !important;
    font-size:0.82rem !important; font-weight:500 !important; padding:6px 14px !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background:#21262d !important; color:#e6edf3 !important;
}
[data-testid="stTabs"] [role="tabpanel"] { padding-top:1.2rem !important; }

/* Misc */
[data-testid="stButton"] button {
    background:#21262d; border:1px solid #30363d; color:#8b949e;
    border-radius:8px; font-size:0.8rem; padding:6px 16px; transition:all .2s;
}
[data-testid="stButton"] button:hover { background:#30363d; color:#e6edf3; border-color:#58a6ff; }
.footer { text-align:center; color:#484f58; font-size:0.75rem; padding:1.5rem 0 0.5rem; border-top:1px solid #21262d; margin-top:2rem; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# DATA LAYER
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "emails.db")


@st.cache_data(ttl=30)
def load_data() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT * FROM processed_emails ORDER BY processed_at DESC", conn
        )
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {"is_sensitive": 0, "sensitive_type": None,
                "sent_reply": 0, "reply_draft": "", "summary": "",
                "priority": "", "category": "UPDATES",
                "reply_status": None}
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
    return df


def fmt_time(ts) -> str:
    try:
        return datetime.fromisoformat(str(ts)).strftime("%b %d, %H:%M")
    except Exception:
        return str(ts)[:16] if ts else "—"


def badge_html(cat: str) -> str:
    cat = (cat or "UPDATES").upper()
    return f'<span class="badge b-{cat}">{cat}</span>'


def priority_badge(p: str) -> str:
    if not p:
        return ""
    score = p.split("\n")[0].replace("PRIORITY:", "").strip()
    return f'<span class="badge b-priority">⚡ {score}</span>'


def plotly_base() -> dict:
    return dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#8b949e", font_family="Inter,sans-serif")


CAT_COLORS = {
    "IMPORTANT": "#f85149", "SENSITIVE": "#ff7b72", "SPAM": "#484f58",
    "PROMOTION": "#e3b341", "SOCIAL": "#3fb950", "UPDATES": "#58a6ff",
}
SENS_COLORS = {
    "OTP": "#f85149", "BANK_ALERT": "#e3b341", "PASSWORD_RESET": "#ff7b72",
    "LOGIN_ALERT": "#d29922", "CARD_ALERT": "#ffa657", "FRAUD_ALERT": "#ff7b72",
    "KYC": "#79c0ff", "ACCOUNT_ALERT": "#d2a8ff", "LEGAL": "#7ee787",
    "FINANCIAL": "#56d364", "OTHER_SENSITIVE": "#8b949e",
}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: HERO
# ─────────────────────────────────────────────────────────────────────────────
def render_hero():
    st.markdown("""
<div class="hero-wrap">
  <div class="hero-title">📧 <span>AI</span> Email Assistant</div>
  <div class="hero-sub">Intelligent inbox automation powered by large language models</div>
  <div class="status-dot">System Online</div>
  <div class="tech-pills">
    <span class="tech-pill">📬 Gmail API</span>
    <span class="tech-pill">🤖 OpenRouter AI</span>
    <span class="tech-pill">📱 Telegram</span>
    <span class="tech-pill">🗄️ SQLite</span>
    <span class="tech-pill">🔐 Sensitive Detection</span>
    <span class="tech-pill">⚡ Auto-Reply</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: KPI CARDS
# ─────────────────────────────────────────────────────────────────────────────
def render_kpi(df: pd.DataFrame, sensitive_df: pd.DataFrame):
    total     = len(df)
    important = len(df[df["category"] == "IMPORTANT"])
    n_sens    = len(sensitive_df)
    replied   = int(df["sent_reply"].sum())

    # Human Decision Layer stats
    pending  = int((df["reply_status"] == "PENDING_APPROVAL").sum()) if "reply_status" in df.columns else 0
    approved = int((df["reply_status"] == "APPROVED").sum())         if "reply_status" in df.columns else 0
    ignored  = int((df["reply_status"] == "IGNORED").sum())          if "reply_status" in df.columns else 0
    decision = int(df["reply_status"].isin(["PENDING_APPROVAL","APPROVED","IGNORED"]).sum()) if "reply_status" in df.columns else 0

    sens_note  = f'<div class="kpi-note note-warn">⚠️ {n_sens} require attention</div>' if n_sens else '<div class="kpi-note note-ok">✅ All clear</div>'
    pend_note  = f'<div class="kpi-note note-warn">⏳ Awaiting your action</div>' if pending else '<div class="kpi-note note-ok">✅ All actioned</div>'

    # Row 1 — existing 4 cards
    st.markdown(f"""
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:10px;">
  <div class="kpi-card kpi-blue">
    <span class="kpi-icon">📨</span>
    <div class="kpi-value">{total}</div>
    <div class="kpi-label">Total Emails</div>
    <div class="kpi-note note-ok">Processed by AI</div>
  </div>
  <div class="kpi-card kpi-red">
    <span class="kpi-icon">🔴</span>
    <div class="kpi-value">{important}</div>
    <div class="kpi-label">Important</div>
    <div class="kpi-note note-warn">Needs attention</div>
  </div>
  <div class="kpi-card kpi-orange">
    <span class="kpi-icon">🔐</span>
    <div class="kpi-value">{n_sens}</div>
    <div class="kpi-label">Sensitive</div>
    {sens_note}
  </div>
  <div class="kpi-card kpi-green">
    <span class="kpi-icon">🤖</span>
    <div class="kpi-value">{replied}</div>
    <div class="kpi-label">Auto Replies Sent</div>
    <div class="kpi-note note-ok">AI-generated</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # Row 2 — Human Decision Layer cards
    st.markdown(f"""
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:1.8rem;">
  <div class="kpi-card" style="border-top:2px solid #e3b341;">
    <span class="kpi-icon">🕐</span>
    <div class="kpi-value" style="color:#e3b341;">{pending}</div>
    <div class="kpi-label">Pending Approval</div>
    {pend_note}
  </div>
  <div class="kpi-card" style="border-top:2px solid #3fb950;">
    <span class="kpi-icon">✅</span>
    <div class="kpi-value" style="color:#3fb950;">{approved}</div>
    <div class="kpi-label">Approved Replies</div>
    <div class="kpi-note note-ok">User approved</div>
  </div>
  <div class="kpi-card" style="border-top:2px solid #484f58;">
    <span class="kpi-icon">❌</span>
    <div class="kpi-value" style="color:#8b949e;">{ignored}</div>
    <div class="kpi-label">Ignored Emails</div>
    <div class="kpi-note" style="color:#484f58;">No reply sent</div>
  </div>
  <div class="kpi-card" style="border-top:2px solid #d2a8ff;">
    <span class="kpi-icon">🧠</span>
    <div class="kpi-value" style="color:#d2a8ff;">{decision}</div>
    <div class="kpi-label">Decision Emails</div>
    <div class="kpi-note" style="color:#7d8590;">Required your input</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: PIPELINE — native Streamlit columns (no HTML loops)
# ─────────────────────────────────────────────────────────────────────────────
def render_pipeline(df: pd.DataFrame, sensitive_df: pd.DataFrame):
    total     = len(df)
    important = len(df[df["category"] == "IMPORTANT"])
    sensitive = len(sensitive_df)
    replied   = int(df["sent_reply"].sum())

    steps = [
        ("📬", "Gmail Fetch",          total),
        ("🧠", "AI Classification",    total),
        ("⚡", "Priority Analysis",    total),
        ("🔐", "Sensitive Detection",  sensitive),
        ("✍️",  "Reply Generation",     important),
        ("📱", "Telegram Notify",      total),
    ]

    st.markdown('<div class="sec-title">⚙️ AI Processing Pipeline</div>', unsafe_allow_html=True)

    cols = st.columns(len(steps))
    for col, (icon, label, count) in zip(cols, steps):
        with col:
            # Each step rendered as a simple static HTML block — no loop variable in HTML
            st.markdown(f"""
<div class="pipe-card">
  <div class="pipe-icon-big">{icon}</div>
  <div class="pipe-lbl">{label}</div>
  <div class="pipe-cnt">{count} emails</div>
</div>
""", unsafe_allow_html=True)

    # Arrow row between steps (decorative, rendered separately)
    st.markdown(
        '<div style="text-align:center;color:#30363d;font-size:0.8rem;'
        'margin-top:6px;letter-spacing:12px;">› › › › ›</div>',
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DONUT CHART
# ─────────────────────────────────────────────────────────────────────────────
def render_donut(df: pd.DataFrame, chart_key: str = "donut"):
    if df.empty or "category" not in df.columns:
        return
    counts = df["category"].value_counts().reset_index()
    counts.columns = ["Category", "Count"]
    colors = [CAT_COLORS.get(c, "#8b949e") for c in counts["Category"]]

    fig = go.Figure(go.Pie(
        labels=counts["Category"], values=counts["Count"],
        hole=0.62,
        marker=dict(colors=colors, line=dict(color="#0d1117", width=2)),
        textinfo="label+percent",
        textfont=dict(size=11, color="#8b949e"),
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>",
    ))
    fig.add_annotation(
        text=f"<b>{counts['Count'].sum()}</b><br><span style='font-size:11px'>emails</span>",
        x=0.5, y=0.5, font=dict(size=20, color="#e6edf3"), showarrow=False, align="center",
    )
    fig.update_layout(
        **plotly_base(),
        margin=dict(t=10, b=10, l=10, r=10), height=270,
        showlegend=True,
        legend=dict(font=dict(color="#7d8590", size=11), bgcolor="rgba(0,0,0,0)",
                    orientation="v", x=1, y=0.5),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=chart_key)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: HORIZONTAL BAR
# ─────────────────────────────────────────────────────────────────────────────
def render_bar(df: pd.DataFrame, chart_key: str = "bar"):
    if df.empty:
        return
    counts = df["category"].value_counts().reset_index()
    counts.columns = ["Category", "Count"]
    bar_colors = [CAT_COLORS.get(c, "#8b949e") for c in counts["Category"]]

    fig = go.Figure(go.Bar(
        x=counts["Count"], y=counts["Category"], orientation="h",
        marker=dict(color=bar_colors, line=dict(width=0)),
        text=counts["Count"], textposition="outside",
        textfont=dict(color="#7d8590", size=11),
        hovertemplate="<b>%{y}</b>: %{x}<extra></extra>",
    ))
    fig.update_layout(
        **plotly_base(),
        margin=dict(t=10, b=10, l=10, r=40), height=220,
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, tickfont=dict(color="#7d8590", size=11),
                   categoryorder="total ascending"),
        bargap=0.35,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=chart_key)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: TIMELINE
# ─────────────────────────────────────────────────────────────────────────────
def render_timeline(df: pd.DataFrame):
    if df.empty or "processed_at" not in df.columns:
        return
    df2 = df.copy()
    df2["date"] = pd.to_datetime(df2["processed_at"], errors="coerce").dt.date
    daily = df2.groupby("date").size().reset_index(name="count").sort_values("date")
    if len(daily) < 2:
        return

    fig = go.Figure(go.Scatter(
        x=daily["date"], y=daily["count"],
        mode="lines+markers",
        line=dict(color="#58a6ff", width=2),
        marker=dict(color="#58a6ff", size=5),
        fill="tozeroy", fillcolor="rgba(88,166,255,0.07)",
        hovertemplate="<b>%{x}</b>: %{y} emails<extra></extra>",
    ))
    fig.update_layout(
        **plotly_base(),
        margin=dict(t=10, b=30, l=40, r=10), height=180,
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(color="#484f58", size=10)),
        yaxis=dict(showgrid=True, gridcolor="#21262d", zeroline=False,
                   tickfont=dict(color="#484f58", size=10)),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="timeline")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: EMAIL CARDS — each card is its own st.markdown call
# ─────────────────────────────────────────────────────────────────────────────
def render_email_cards(rows: list, max_cards: int = 15):
    if not rows:
        st.markdown("""
<div class="empty-state">
  <div class="empty-icon">📭</div>
  <div class="empty-title">No emails here yet</div>
  <div class="empty-sub">Run <code>python main.py</code> to start</div>
</div>
""", unsafe_allow_html=True)
        return

    for row in rows[:max_cards]:
        is_sens = int(row.get("is_sensitive", 0)) == 1
        cat     = "SENSITIVE" if is_sens else str(row.get("category", "UPDATES")).upper()
        subject = row.get("subject", "(No Subject)")
        sender  = row.get("sender_email", "—")
        ts      = fmt_time(row.get("processed_at", ""))
        pri     = row.get("priority", "")
        replied = int(row.get("sent_reply", 0)) == 1

        b_cat     = badge_html(cat)
        b_pri     = priority_badge(pri)
        b_replied = '<span class="badge b-replied">✅ Replied</span>' if replied else ""
        b_sens    = '<span class="badge b-SENSITIVE">🔐 SENSITIVE</span>' if is_sens else ""
        card_cls  = "email-card sens" if is_sens else "email-card"

        # Each card is one standalone static HTML block
        st.markdown(f"""
<div class="{card_cls}">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:5px;">
    <div class="email-subj">{subject}</div>
    <div style="display:flex;gap:4px;flex-wrap:wrap;flex-shrink:0;">
      {b_cat} {b_pri} {b_replied} {b_sens}
    </div>
  </div>
  <div class="email-meta-row">
    <span class="email-sender">✉️ {sender}</span>
    <span class="email-time">🕐 {ts}</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: SENSITIVE TAB
# ─────────────────────────────────────────────────────────────────────────────
def render_sensitive_tab(sensitive_df: pd.DataFrame):
    if sensitive_df.empty:
        st.markdown("""
<div class="empty-state" style="padding:2.5rem 1rem;">
  <div class="empty-icon">🛡️</div>
  <div class="empty-title">No sensitive emails detected</div>
  <div class="empty-sub">The AI monitor watches for OTPs, bank alerts, password resets, and more.</div>
</div>
""", unsafe_allow_html=True)
        st.markdown('<div class="sec-title" style="margin-top:1rem;">🔐 Detection capabilities</div>',
                    unsafe_allow_html=True)
        caps = [
            ("🔑", "OTPs & verification codes"),    ("🏦", "Bank transaction alerts"),
            ("🔓", "Password reset emails"),         ("🚨", "Login / sign-in alerts"),
            ("💳", "Card transaction alerts"),       ("⚠️",  "Fraud warnings"),
            ("📋", "KYC / identity verification"),  ("🔒", "Account security alerts"),
            ("⚖️",  "Legal notices"),                 ("💰", "Financial documents"),
        ]
        c1, c2 = st.columns(2)
        for i, (icon, label) in enumerate(caps):
            with (c1 if i % 2 == 0 else c2):
                st.markdown(
                    f'<div style="font-size:0.82rem;color:#7d8590;padding:4px 0;">{icon} {label}</div>',
                    unsafe_allow_html=True
                )
        return

    st.markdown(
        f'<div class="sens-banner">🚨 <strong>{len(sensitive_df)} sensitive email(s) detected.</strong>'
        f' All codes are masked. Auto-replies are disabled. Open Gmail to view originals.</div>',
        unsafe_allow_html=True
    )

    # Sensitive type chart
    if "sensitive_type" in sensitive_df.columns:
        tc = sensitive_df["sensitive_type"].dropna().value_counts().reset_index()
        tc.columns = ["Type", "Count"]
        if not tc.empty:
            st.markdown('<div class="sec-title">🔎 Detection breakdown</div>', unsafe_allow_html=True)
            fig = go.Figure(go.Bar(
                x=tc["Type"], y=tc["Count"],
                marker=dict(color=[SENS_COLORS.get(t, "#8b949e") for t in tc["Type"]], line=dict(width=0)),
                text=tc["Count"], textposition="outside",
                textfont=dict(color="#7d8590", size=11),
                hovertemplate="<b>%{x}</b>: %{y}<extra></extra>",
            ))
            fig.update_layout(
                **plotly_base(),
                margin=dict(t=10, b=10, l=10, r=10), height=200,
                xaxis=dict(showgrid=False, tickfont=dict(color="#7d8590", size=10)),
                yaxis=dict(showgrid=False, showticklabels=False),
                bargap=0.35,
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="sens_type_chart")

    st.markdown('<div class="sec-title">🔐 Sensitive emails</div>', unsafe_allow_html=True)
    render_email_cards(sensitive_df.to_dict("records"), max_cards=20)

    # Detail viewer
    st.markdown('<div class="sec-title" style="margin-top:1.4rem;">🔍 Inspect</div>',
                unsafe_allow_html=True)
    st.caption("⚠️ All codes masked — safe to view")
    sel = st.selectbox("Select email:", sensitive_df["subject"].tolist(), key="sens_sel")
    if not sel:
        return
    row = sensitive_df[sensitive_df["subject"] == sel].iloc[0]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div style="font-size:0.72rem;color:#7d8590;margin-bottom:3px;">From</div>'
                    f'<div style="font-size:0.85rem;color:#58a6ff;">{row.get("sender_email","—")}</div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div style="font-size:0.72rem;color:#7d8590;margin-bottom:3px;">Type</div>'
                    f'<div style="font-size:0.85rem;color:#ff7b72;">🔐 {row.get("sensitive_type","—")}</div>',
                    unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div style="font-size:0.72rem;color:#7d8590;margin-bottom:3px;">Processed</div>'
                    f'<div style="font-size:0.85rem;color:#8b949e;">{fmt_time(row.get("processed_at",""))}</div>',
                    unsafe_allow_html=True)
    summary = str(row.get("summary", "")).strip()
    if summary:
        st.markdown('<div style="margin-top:1rem;font-size:0.72rem;color:#7d8590;font-weight:600;'
                    'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">AI Summary (masked)</div>',
                    unsafe_allow_html=True)
        st.info(summary)
    st.caption("🔒 OTPs and codes replaced with [CODE MASKED]")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: AUTO-REPLIES TAB
# ─────────────────────────────────────────────────────────────────────────────
def render_replies_tab(df: pd.DataFrame):
    replied_df = df[df["sent_reply"] == 1]
    if replied_df.empty:
        st.markdown("""
<div class="empty-state" style="padding:2.5rem 1rem;">
  <div class="empty-icon">🤖</div>
  <div class="empty-title">No auto-replies sent yet</div>
  <div class="empty-sub">IMPORTANT emails receive AI-generated replies automatically.</div>
</div>
""", unsafe_allow_html=True)
        return

    st.markdown(f'<div class="sec-title">🤖 Auto-reply history &nbsp;'
                f'<span style="font-size:0.75rem;color:#58a6ff;font-weight:400;">'
                f'{len(replied_df)} sent</span></div>', unsafe_allow_html=True)

    for row in replied_df.to_dict("records"):
        subject   = row.get("subject", "(No Subject)")
        sender    = row.get("sender_email", "—")
        ts        = fmt_time(row.get("processed_at", ""))
        reply_txt = str(row.get("reply_draft", "")).strip() or "Reply content not stored."
        cat       = str(row.get("category", "")).upper()

        # Static block per card — no loop-embedded HTML string
        st.markdown(f"""
<div class="reply-card">
  <div class="reply-hdr">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
      <div>
        <div class="reply-subj">{subject}</div>
        <div class="reply-to">To: {sender}</div>
      </div>
      <div style="display:flex;gap:6px;align-items:center;flex-shrink:0;">
        {badge_html(cat)}
        <span style="font-size:0.72rem;color:#484f58;">{ts}</span>
        <span class="badge b-replied">✅ Replied</span>
      </div>
    </div>
  </div>
  <div class="reply-body-w">
    <div class="reply-lbl">Generated reply</div>
    <div class="reply-txt">{reply_txt}</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: ANALYTICS TAB
# ─────────────────────────────────────────────────────────────────────────────
def render_analytics_tab(df: pd.DataFrame, sensitive_df: pd.DataFrame):
    st.markdown('<div class="sec-title">📊 Category distribution</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        render_donut(df, chart_key="donut_analytics")
    with c2:
        render_bar(df, chart_key="bar_analytics")

    st.markdown('<div class="sec-title" style="margin-top:1rem;">📈 Processing timeline</div>',
                unsafe_allow_html=True)
    render_timeline(df)

    st.markdown('<div class="sec-title" style="margin-top:1rem;">📋 Statistics</div>',
                unsafe_allow_html=True)

    total     = len(df)
    replied   = int(df["sent_reply"].sum())
    reply_rate = round(replied / total * 100) if total else 0

    stats = [
        ("📨", "Total",      total,                                    "#58a6ff"),
        ("🔴", "Important",  len(df[df["category"] == "IMPORTANT"]),   "#f85149"),
        ("🚫", "Spam",       len(df[df["category"] == "SPAM"]),        "#484f58"),
        ("📢", "Promotions", len(df[df["category"] == "PROMOTION"]),   "#e3b341"),
        ("💬", "Social",     len(df[df["category"] == "SOCIAL"]),      "#3fb950"),
        ("🔔", "Updates",    len(df[df["category"] == "UPDATES"]),     "#79c0ff"),
        ("🔐", "Sensitive",  len(sensitive_df),                        "#ff7b72"),
        ("✅", "Replied",    replied,                                   "#3fb950"),
    ]

    cols = st.columns(4)
    for i, (icon, label, val, color) in enumerate(stats):
        with cols[i % 4]:
            # One static block each — no dynamic HTML inside loops
            st.markdown(
                f'<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;'
                f'padding:1rem;margin-bottom:10px;text-align:center;">'
                f'<div style="font-size:1.4rem;">{icon}</div>'
                f'<div style="font-size:1.5rem;font-weight:700;color:{color};margin:4px 0;">{val}</div>'
                f'<div style="font-size:0.72rem;color:#7d8590;text-transform:uppercase;'
                f'letter-spacing:0.5px;">{label}</div></div>',
                unsafe_allow_html=True
            )

    if total > 0:
        st.markdown(
            f'<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;'
            f'padding:1rem 1.4rem;margin-top:6px;display:flex;align-items:center;'
            f'justify-content:space-between;flex-wrap:wrap;gap:12px;">'
            f'<div style="font-size:0.82rem;color:#7d8590;">Reply rate for IMPORTANT emails</div>'
            f'<div style="font-size:1.2rem;font-weight:700;color:#58a6ff;">{reply_rate}%</div></div>',
            unsafe_allow_html=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: EMAIL DETAIL TAB
# ─────────────────────────────────────────────────────────────────────────────
def render_detail_tab(df: pd.DataFrame):
    if df.empty:
        return
    selected = st.selectbox("Select an email:", df["subject"].tolist(), key="detail_sel")
    if not selected:
        return
    row     = df[df["subject"] == selected].iloc[0]
    is_sens = int(row.get("is_sensitive", 0)) == 1
    cat     = str(row.get("category", "UPDATES")).upper()
    pri     = row.get("priority", "")
    summary = str(row.get("summary", "")).strip()
    reply   = str(row.get("reply_draft", "")).strip()
    replied = int(row.get("sent_reply", 0)) == 1

    if is_sens:
        st.markdown(
            f'<div class="sens-banner">🔐 <strong>Sensitive email</strong> — '
            f'Type: {row.get("sensitive_type","Unknown")}. Content is masked. Auto-reply disabled.</div>',
            unsafe_allow_html=True
        )

    # Meta row using native columns + static HTML
    c1, c2, c3, c4 = st.columns(4)
    meta_items = [
        (c1, "From",      row.get("sender_email","—"),          "#58a6ff"),
        (c2, "Category",  cat,                                   "#e6edf3"),
        (c3, "Processed", fmt_time(row.get("processed_at","")), "#8b949e"),
        (c4, "Replied",   "✅ Yes" if replied else "🚫 No",     "#3fb950" if replied else "#484f58"),
    ]
    for col, label, val, color in meta_items:
        with col:
            st.markdown(
                f'<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;'
                f'padding:0.8rem 1rem;">'
                f'<div style="font-size:0.72rem;color:#7d8590;margin-bottom:4px;'
                f'text-transform:uppercase;letter-spacing:0.5px;">{label}</div>'
                f'<div style="font-size:0.88rem;font-weight:600;color:{color};">{val}</div></div>',
                unsafe_allow_html=True
            )

    # Priority breakdown
    if pri:
        lines = [l.strip() for l in pri.strip().split("\n") if ":" in l]
        p_cols = st.columns(len(lines))
        for pc, line in zip(p_cols, lines):
            parts = line.split(":", 1)
            with pc:
                st.markdown(
                    f'<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;'
                    f'padding:0.7rem 1rem;text-align:center;margin-top:10px;">'
                    f'<div style="font-size:0.7rem;color:#7d8590;margin-bottom:3px;'
                    f'text-transform:uppercase;">{parts[0].strip()}</div>'
                    f'<div style="font-size:1.1rem;font-weight:700;color:#58a6ff;">'
                    f'{parts[1].strip()}</div></div>',
                    unsafe_allow_html=True
                )

    if summary:
        st.markdown(
            '<div style="margin-top:1.2rem;font-size:0.72rem;color:#7d8590;font-weight:600;'
            'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">🤖 AI Summary</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div style="background:#161b22;border:1px solid #30363d;border-left:3px solid #58a6ff;'
            f'border-radius:10px;padding:1rem 1.2rem;font-size:0.84rem;color:#8b949e;line-height:1.8;">'
            f'{summary}</div>',
            unsafe_allow_html=True
        )

    if not is_sens and reply:
        st.markdown(
            '<div style="margin-top:1.2rem;font-size:0.72rem;color:#7d8590;font-weight:600;'
            'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">✉️ Reply Draft</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div style="background:#161b22;border:1px solid #30363d;border-left:3px solid #3fb950;'
            f'border-radius:10px;padding:1rem 1.2rem;font-size:0.84rem;color:#8b949e;'
            f'line-height:1.8;white-space:pre-wrap;">{reply}</div>',
            unsafe_allow_html=True
        )
    elif is_sens:
        st.caption("🔒 Reply draft hidden — sensitive email")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION: PENDING APPROVALS TAB
# ─────────────────────────────────────────────────────────────────────────────
def render_pending_tab(df: pd.DataFrame):
    """Render the Pending Approvals tab — emails awaiting human decision."""

    if "reply_status" not in df.columns:
        pending_df = pd.DataFrame()
    else:
        pending_df = df[df["reply_status"] == "PENDING_APPROVAL"]

    if pending_df.empty:
        st.markdown("""
<div class="empty-state" style="padding:2.5rem 1rem;">
  <div class="empty-icon">🧠</div>
  <div class="empty-title">No pending approvals</div>
  <div class="empty-sub">When an email requires your personal decision, it appears here.<br>
  Use the Telegram inline buttons to approve, edit, or ignore.</div>
</div>
""", unsafe_allow_html=True)

        # Explain the workflow
        st.markdown('<div class="sec-title" style="margin-top:1rem;">🔄 How it works</div>',
                    unsafe_allow_html=True)
        steps = [
            ("🧠", "AI detects emails requiring personal decisions"),
            ("🚫", "Auto-reply is blocked — no email sent automatically"),
            ("📱", "Telegram alert sent with inline buttons"),
            ("✅", "You choose: Send Draft / Edit Reply / Ignore"),
            ("📊", "Status tracked here on the dashboard"),
        ]
        c1, c2 = st.columns(2)
        for i, (icon, label) in enumerate(steps):
            with (c1 if i % 2 == 0 else c2):
                st.markdown(
                    f'<div style="font-size:0.82rem;color:#7d8590;padding:5px 0;">{icon} {label}</div>',
                    unsafe_allow_html=True
                )
        return

    # Banner
    st.markdown(
        f'<div style="background:rgba(227,179,65,.08);border:1px solid rgba(227,179,65,.3);'
        f'border-radius:10px;padding:1rem 1.2rem;margin-bottom:1.2rem;'
        f'font-size:0.85rem;color:#e3b341;font-weight:500;">'
        f'⏳ <strong>{len(pending_df)} email(s) awaiting your decision.</strong>'
        f' Use the Telegram inline buttons to approve, edit, or ignore.</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="sec-title">🧠 Emails requiring your decision</div>',
                unsafe_allow_html=True)

    for row in pending_df.to_dict("records"):
        subject  = row.get("subject", "(No Subject)")
        sender   = row.get("sender_email", "—")
        ts       = fmt_time(row.get("processed_at", ""))
        draft    = str(row.get("reply_draft", "")).strip()
        summary  = str(row.get("summary", "")).strip()
        priority = row.get("priority", "")
        b_pri    = priority_badge(priority)

        draft_preview = (draft[:250] + "...") if len(draft) > 250 else draft

        st.markdown(f"""
<div class="pending-card">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:6px;">
    <div class="email-subj">{subject}</div>
    <div style="display:flex;gap:4px;flex-wrap:wrap;flex-shrink:0;">
      <span class="badge b-PENDING_APPROVAL">⏳ PENDING</span>
      {b_pri}
    </div>
  </div>
  <div class="email-meta-row">
    <span class="email-sender">✉️ {sender}</span>
    <span class="email-time">🕐 {ts}</span>
  </div>
  <div style="font-size:0.72rem;color:#7d8590;font-weight:600;text-transform:uppercase;"
       style="margin-top:8px;letter-spacing:0.5px;">🤖 AI Draft</div>
  <div class="pending-draft">{draft_preview or '(No draft stored)'}</div>
  <div style="margin-top:8px;font-size:0.72rem;color:#484f58;">
    📱 Action via Telegram: ✅ Send Draft &nbsp;·&nbsp; ✏️ Edit Reply &nbsp;·&nbsp; ❌ Ignore
  </div>
</div>
""", unsafe_allow_html=True)

    # Decision history — approved + ignored
    if "reply_status" in df.columns:
        history_df = df[df["reply_status"].isin(["APPROVED", "IGNORED", "AUTO_SENT"])]
        if not history_df.empty:
            st.markdown('<div class="sec-title" style="margin-top:1.4rem;">📜 Decision History</div>',
                        unsafe_allow_html=True)
            for row in history_df.head(10).to_dict("records"):
                status  = str(row.get("reply_status", "")).upper()
                subject = row.get("subject", "(No Subject)")
                sender  = row.get("sender_email", "—")
                ts      = fmt_time(row.get("processed_at", ""))

                status_icon = {
                    "AUTO_SENT": "🤖", "APPROVED": "✅", "IGNORED": "❌"
                }.get(status, "❓")
                status_color = {
                    "AUTO_SENT": "#3fb950", "APPROVED": "#3fb950", "IGNORED": "#484f58"
                }.get(status, "#8b949e")

                st.markdown(
                    f'<div style="background:#161b22;border:1px solid #21262d;border-radius:10px;'
                    f'padding:0.7rem 1rem;margin-bottom:6px;display:flex;align-items:center;'
                    f'justify-content:space-between;gap:12px;">'
                    f'<div>'
                    f'<div style="font-size:0.85rem;font-weight:600;color:#e6edf3;">{subject}</div>'
                    f'<div style="font-size:0.75rem;color:#58a6ff;margin-top:2px;">✉️ {sender}</div>'
                    f'</div>'
                    f'<div style="display:flex;gap:8px;align-items:center;flex-shrink:0;">'
                    f'<span style="font-size:0.72rem;color:#484f58;">{ts}</span>'
                    f'<span style="font-size:0.8rem;font-weight:600;color:{status_color};">{status_icon} {status}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    df = load_data()
    df = ensure_cols(df)
    sensitive_df = df[df["is_sensitive"] == 1]

    render_hero()

    if df.empty:
        st.markdown("""
<div class="empty-state">
  <div class="empty-icon">📭</div>
  <div class="empty-title">No emails processed yet</div>
  <div class="empty-sub">Run <code>python main.py</code> to start the AI pipeline, then refresh.</div>
</div>
""", unsafe_allow_html=True)
        return

    render_kpi(df, sensitive_df)
    render_pipeline(df, sensitive_df)

    # Pending approvals count for tab label
    pending_count = int((df["reply_status"] == "PENDING_APPROVAL").sum()) if "reply_status" in df.columns else 0

    tab_emails, tab_pending, tab_sensitive, tab_replies, tab_analytics, tab_detail = st.tabs([
        "📋 Recent Emails",
        f"🧠 Pending Approvals  {pending_count}" if pending_count else "🧠 Pending Approvals",
        f"🔐 Sensitive  {len(sensitive_df)}",
        f"🤖 Auto-Replies  {int(df['sent_reply'].sum())}",
        "📊 Analytics",
        "🔍 Email Detail",
    ])

    with tab_emails:
        left, right = st.columns([1, 2])
        with left:
            st.markdown('<div class="sec-title">🍩 Category distribution</div>', unsafe_allow_html=True)
            render_donut(df, chart_key="donut_recent")
        with right:
            st.markdown('<div class="sec-title">📨 Recent emails</div>', unsafe_allow_html=True)
            render_email_cards(df.to_dict("records"), max_cards=12)

    with tab_pending:
        render_pending_tab(df)

    with tab_sensitive:
        render_sensitive_tab(sensitive_df)

    with tab_replies:
        render_replies_tab(df)

    with tab_analytics:
        render_analytics_tab(df, sensitive_df)

    with tab_detail:
        render_detail_tab(df)

    # Footer
    c_btn, c_cap = st.columns([1, 5])
    with c_btn:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()
    with c_cap:
        st.markdown(
            f'<div style="font-size:0.75rem;color:#484f58;padding-top:0.4rem;">'
            f'Auto-refreshes every 30s &nbsp;·&nbsp; DB: {DB_PATH} &nbsp;·&nbsp;'
            f' {len(df)} emails processed</div>',
            unsafe_allow_html=True
        )
    st.markdown('<div class="footer">AI Email Assistant · Gmail · OpenRouter · Telegram · SQLite</div>',
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()