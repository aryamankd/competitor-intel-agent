# Workday Competitor Intelligence Agent
**Business Foundations AI — Project Submission**

---

## 1. Agent Overview

This agent is a **Competitor Intelligence Analyst** for Workday, a leading provider of enterprise Human Capital Management (HCM) and financial management software serving organizations with 1,000+ employees globally. The agent monitors publicly available signals from Workday's key competitors, filters for strategic relevance, and produces a structured intelligence brief for Workday's product, sales, and executive teams.

The agent answers the question: *"What are our competitors doing right now, and what should Workday do about it?"*

---

## 2. Competitor Scope

The agent monitors three primary competitors selected for their direct overlap with Workday's core HCM and payroll market:

| Competitor | Relevance to Workday |
|---|---|
| **SAP SuccessFactors** | Largest direct competitor in enterprise HCM |
| **Oracle HCM Cloud** | Head-to-head in large enterprise and finance |
| **Rippling** | Fast-growing challenger in mid-market HR + IT |

**Why three instead of six:** Each competitor triggers multiple server-side web searches across signal categories. With 6 competitors and 7 signal categories, a single run executes 40+ searches, flooding the context window with search results. When `pause_turn` continuations occur, that entire history is re-sent as input tokens — causing costs to spike well above $2 per run. Reducing to 3 competitors cuts search volume roughly in half and keeps runs within budget. ADP Workforce Now, Ceridian Dayforce, and UKG can be added back via `COMPETITORS` in `agent.py` if cost is not a constraint.

**Why these three:** SAP and Oracle represent Workday's primary enterprise displacement risk. Rippling is the most strategically relevant challenger in the mid-market segment Workday is actively expanding into.

---

## 3. Signal Sources

The agent uses **Claude's built-in web search tool** (`web_search_20260209`) to query public sources at runtime. No proprietary data feeds or scrapers are required.

| Signal Category | Example Sources |
|---|---|
| Product launches and feature releases | Official newsrooms, product blogs, release notes |
| AI/ML capabilities and roadmap signals | Conference announcements, developer docs, demo videos |
| Hiring patterns | LinkedIn job postings, Greenhouse/Lever job boards |
| Partnership and integration news | Partner pages, press releases, ecosystem announcements |
| Pricing and packaging changes | Pricing pages, G2 reviews, sales enablement leaks |
| Customer wins and analyst coverage | Gartner/IDC reports, case studies, press mentions |
| Messaging and positioning shifts | Homepage copy, ad campaigns, conference keynotes |

**Why web search over a static database:** Competitor intelligence has a short shelf life. A pre-indexed database requires maintenance infrastructure and becomes stale within weeks. A web search tool queries live sources at run time, ensuring the brief reflects current reality — not a snapshot from last quarter.

### Source Quality Policy

Sources are ranked by reliability tier. Claude is instructed to prefer higher tiers and to state the tier and publication date for every signal:

| Tier | Sources | Usage |
|---|---|---|
| **Tier 1 (HIGH)** | Official newsrooms, product release notes, SEC filings | Required for high-impact claims |
| **Tier 2 (MED)** | TechCrunch, WSJ, Bloomberg, G2/Gartner/IDC reports | Acceptable for all signals |
| **Tier 3 (LOW)** | LinkedIn posts, job boards, forums, anonymous reviews | Supporting evidence only |

**Evidence thresholds:**
- High-impact claims (pricing changes, major product launches, segment moves): ≥2 independent Tier 1/2 sources required. Claims below this threshold are labelled `LOW_EVIDENCE` and excluded from the Executive Summary.
- Insufficient evidence: if a competitor yields fewer than 2 verifiable signals, the output explicitly states `INSUFFICIENT EVIDENCE — [reason]` rather than fabricating signals.

---

## 4. Monitoring Cadence

| Trigger | Frequency | Rationale |
|---|---|---|
| Scheduled scan | Weekly (every Monday 9am) | Keeps leadership briefed on a predictable cadence |
| Pre-deal research | On-demand | Sales team runs before a competitive deal cycle |
| Event-triggered | After a competitor conference/announcement | Ensures rapid response to major news |

**Recommended deployment:** `cron` or GitHub Actions with the following schedule:
```
0 9 * * 1  cd /path/to/competitor-intel-agent && python3 agent.py >> logs/run.log 2>&1
```
Failed runs (non-zero exit, missing sections) should alert via email or Slack webhook. Output PDFs should be distributed to a restricted internal mailing list, not a public channel.

**Why not real-time or daily:** HCM software moves on product cycles measured in quarters, not hours. Daily scans would surface mostly noise and drive alert fatigue. Weekly scans balance freshness with signal-to-noise ratio.

---

## 5. Agent Architecture

The agent is built using the **Claude API** (`claude-sonnet-4-6`) with Anthropic's server-side web search tool. It runs a streaming agentic loop with a deterministic five-step output structure. A real-time cost guardrail monitors token spend mid-stream and cancels the request if the $2 budget is exceeded.

```
User invokes agent
        │
        ▼
 System prompt (Workday products, competitive position, source policy,
                evidence thresholds, confidence scoring, action catalog)
 User prompt (search plan step → memory reconciliation → brief format)
 + Previous brief injected if memory file exists
        │
        ▼
 Step 0: Memory reconciliation — verify top 3 prior claims before searching
        │
        ▼
 Step 1: Claude outputs explicit search plan (competitor | query | source type)
        │
        ▼
 Claude streams response → web_search tool executes server-side
        │   ↑
        │   └── loop until end_turn or pause_turn (max 2 continuations)
        │         cost guardrail checked on every streaming event
        ▼
 Steps 2–5: Executive Summary → Competitor Signals → Risk Radar → Signal Gaps
        │
        ▼
 Completeness validation (required sections + per-competitor coverage check)
        │
        ▼
 PDF report + JSON saved to disk
 Memory file updated for next run
```

**Key design decisions:**

- **Workday-specific system prompt:** Encodes Workday's five core products, known strengths and vulnerabilities, audience definitions (VP Product, Sales Enablement, CPO), source quality tiers, evidence thresholds, confidence scoring (A/B/C), and an action catalog. This means Claude reasons like an internal analyst rather than a generic summarizer.
- **Deterministic five-step output structure:** The user prompt enforces a fixed output sequence (Search Plan → Executive Summary → Competitor Signals → Risk Radar → Signal Gaps). Each step has a defined schema, preventing free-form narrative drift.
- **Explicit search plan (Step 1):** Claude is required to output its search plan as `competitor | query | source type` before executing searches. This makes reasoning inspectable and auditable rather than a black box.
- **Memory reconciliation (Step 0):** On delta runs, the agent verifies the top 3 prior claims against current sources before proceeding. Claims contradicted by new evidence are marked `RETRACTED`. This prevents anchoring errors from compounding across runs.
- **`claude-sonnet-4-6` over `claude-opus-4-6`:** Sonnet is ~5x cheaper ($3/$15 per million tokens vs $15/$75) with no meaningful quality drop for a search-and-summarize task.
- **No adaptive thinking:** Removed — added significant hidden token spend without proportional output quality improvement for this use case.
- **Streaming with mid-stream cost cancellation:** Rather than blocking on a single `messages.create()` call, the agent streams the response. On every `message_start` and `content_block_delta` event, cumulative cost is estimated. If the $2 limit is hit mid-response, the stream is closed and partial results are returned with a warning.
- **5-minute hard timeout:** Anthropic client initialized with `timeout=300.0` as a safety net if the stream stalls before the cost guardrail fires.
- **Output completeness validation:** After the agentic loop, the output is checked for all required sections and per-competitor coverage. Missing sections trigger a warning rather than a silent partial brief.
- **PDF output:** The brief is rendered as a formatted PDF using `fpdf2`, ready to forward to stakeholders without editing.

---

## 6. Scoring Framework

Every signal in the Competitor Signals section is scored on three dimensions:

| Dimension | Scale | Description |
|---|---|---|
| **Impact on Workday** | 1–5 | How significantly would this affect Workday's revenue, market position, or product roadmap if it materialises? |
| **Likelihood (deal impact)** | 1–5 | How likely is this to affect an active deal or renewal within the next 6 months? |
| **Time horizon** | NEAR / MID / LONG | <3 months / 3–9 months / 9+ months |

**Risk score** (used in Risk Radar) = Impact × Likelihood (max 25).

**Confidence levels** are assigned based on source evidence:
- **A** — 2+ independent Tier 1/2 sources with dates within 90 days
- **B** — 1 Tier 1/2 source, or 2+ Tier 3 sources with dates
- **C** — single Tier 3 source, or undated source

Confidence C signals are excluded from the Executive Summary. They appear in Competitor Signals with a warning.

**Action catalog:** Recommended actions are constrained to a fixed taxonomy to prevent vague advice:

| Action | Trigger condition |
|---|---|
| `BATTLECARD_UPDATE` | Competitor pricing change, new feature in Workday's core area |
| `ROADMAP_FLAG` | Competitor investing in area where Workday leads (Skills Cloud, Planning) |
| `PRICING_ALERT` | Confirmed discounting or packaging change with Tier 1/2 evidence |
| `PARTNER_WATCH` | New partnership that extends competitor platform reach into Workday's territory |
| `MONITOR` | Signal noted but insufficient evidence or long time horizon |

Each action includes an owner (Sales Enablement / Product Strategy / Executive / Marketing).

---

## 7. Code

```python
# agent.py — core agent logic (simplified for readability)
# Full implementation at agent.py in this repo

import anthropic
import sys
from datetime import datetime

MODEL = "claude-sonnet-4-6"
MAX_COST_USD = 2.00
_INPUT_PRICE_PER_M  = 3.00
_OUTPUT_PRICE_PER_M = 15.00

COMPETITORS = ["SAP SuccessFactors", "Oracle HCM Cloud", "Rippling"]

SIGNAL_CATEGORIES = [
    "product launches and feature releases",
    "AI and automation capabilities",
    "hiring patterns and job postings that signal strategic priorities",
    "partnership and integration announcements",
    "pricing or packaging changes",
    "customer wins and analyst coverage",
    "messaging and positioning shifts",
]

def _estimate_cost(input_tokens, output_tokens):
    return (input_tokens / 1_000_000 * _INPUT_PRICE_PER_M
            + output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_M)

def run_intelligence_scan(competitors, focus_areas=None, previous_brief=None,
                          max_continuations=2):
    client = anthropic.Anthropic(timeout=300.0)

    signal_list = "\n".join(f"  - {s}" for s in SIGNAL_CATEGORIES)

    # Memory reconciliation step — injected when previous brief exists
    memory_reconciliation = ""
    if previous_brief:
        memory_reconciliation = """
## Step 0 — Memory Reconciliation
Verify the top 3 claims from the previous brief before searching.
Mark each CONFIRMED or RETRACTED with supporting source.
"""

    user_prompt = f"""Conduct a competitor intelligence scan for Workday as of {datetime.now().strftime('%B %d, %Y')}.
Analyze: {', '.join(competitors)}
Signal categories:
{signal_list}
{memory_reconciliation}

### Step 1 — Search Plan
List: [competitor] | [query] | [source type] (2–3 per competitor)

### Step 2 — Executive Summary
3–5 findings (Confidence A/B only), each with source and date.

### Step 3 — Competitor Signals
For each signal:
  Signal / Date / Source (URL, Tier) / Confidence (A/B/C)
  Impact 1–5 / Likelihood 1–5 / Time horizon (NEAR/MID/LONG)
  Strategic implication / Recommended action (BATTLECARD_UPDATE |
  ROADMAP_FLAG | PRICING_ALERT | PARTNER_WATCH | MONITOR) / Owner

### Step 4 — Risk Radar
Rank by Risk Score = Impact × Likelihood. Include time horizon.

### Step 5 — Signal Gaps
Where was evidence below threshold or paywalled?"""

    messages = [{"role": "user", "content": user_prompt}]
    continuations = 0
    total_input_tokens = 0
    total_output_tokens = 0
    content = []
    stop_reason = "end_turn"

    while True:
        call_input_tokens = 0
        accumulated_output_chars = 0
        cost_limit_hit = False

        with client.messages.stream(
            model=MODEL, max_tokens=4000, system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=messages,
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", None)
                if etype == "message_start":
                    call_input_tokens = event.message.usage.input_tokens
                    if _estimate_cost(total_input_tokens + call_input_tokens,
                                      total_output_tokens) >= MAX_COST_USD:
                        cost_limit_hit = True; break
                elif etype == "content_block_delta":
                    accumulated_output_chars += len(getattr(event.delta, "text", "") or "")
                    if _estimate_cost(total_input_tokens + call_input_tokens,
                                      total_output_tokens + accumulated_output_chars // 4
                                      ) >= MAX_COST_USD:
                        cost_limit_hit = True; break

            if cost_limit_hit:
                snapshot = stream.current_message_snapshot
                content = snapshot.content if snapshot else []
                stop_reason = "cost_limit"
            else:
                msg = stream.get_final_message()
                content, call_input_tokens = msg.content, msg.usage.input_tokens
                call_output_tokens = msg.usage.output_tokens
                stop_reason = msg.stop_reason

        total_input_tokens += call_input_tokens
        total_output_tokens += call_output_tokens

        if stop_reason in ("cost_limit", "end_turn"):
            break
        if stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": content})
            continuations += 1
            if continuations >= max_continuations:
                break
            continue
        break

    final_text = "\n".join(b.text for b in content if b.type == "text")

    # Completeness validation
    for section in ["Executive Summary", "Competitor Signals", "Risk Radar", "Signal Gaps"]:
        if section not in final_text:
            print(f"[warn] Missing section: {section}", file=sys.stderr)
    for c in competitors:
        if c.split()[0] not in final_text:
            print(f"[warn] No signals found for {c}", file=sys.stderr)

    return final_text
```

Run with:

```bash
pip3 install anthropic fpdf2
export ANTHROPIC_API_KEY=your_key_here
python3 agent.py
```

---

## 8. Output Format

The agent produces a **five-step structured brief** saved as PDF and JSON:

### Step 1 — Search Plan
Explicit list of `competitor | query | source type` before any searches execute. Makes reasoning inspectable.

### Step 2 — Executive Summary
3–5 highest-priority findings (Confidence A or B only), each with source, date, and delta tag on subsequent runs.

### Step 3 — Competitor Signals
Each signal includes: what happened, publication date, source URL and tier, confidence level, delta tag, impact score (1–5), likelihood score (1–5), time horizon, strategic implication, and a constrained recommended action from the action catalog.

### Step 4 — Risk Radar
Threats ranked by Risk Score = Impact × Likelihood (max 25), with time horizon and escalation triggers.

### Step 5 — Signal Gaps
Where evidence was sparse, paywalled, or below the evidence threshold. Prevents false confidence.

**Who reads this:** VP of Product Strategy (roadmap threats), Head of Sales Enablement (battlecard triggers), Chief People Officer (board narrative).

---

## 9. Limitations and Failure Containment

**What this agent cannot do:**
- **Access paywalled content.** Analyst reports (Gartner Magic Quadrant, IDC MarketScape), private pricing, and internal roadmaps are invisible to web search. The Signal Gaps section surfaces these blind spots explicitly.
- **Monitor in real-time.** This is a batch scan, not a streaming feed.
- **Guarantee accuracy.** Web search can surface inaccurate or outdated content. The source quality tiers, evidence thresholds, and confidence scoring reduce (but do not eliminate) this risk. Outputs should be treated as analyst starting points, not ground truth.

**Failure containment mechanisms:**
- **Evidence thresholds** prevent high-impact claims (pricing, major launches) from appearing without ≥2 independent Tier 1/2 sources.
- **Confidence C exclusion** keeps weak-evidence signals out of the Executive Summary.
- **Memory reconciliation** verifies prior claims before each delta run, preventing anchoring errors from compounding.
- **Insufficient evidence pathway** produces an explicit `INSUFFICIENT EVIDENCE` marker rather than fabricated signals.
- **Completeness validation** warns on missing sections or missing per-competitor coverage after each run.
- **Human review gate:** Outputs should be reviewed by an analyst before distribution to executives. The Signal Gaps and confidence levels provide a natural review checklist.

**Known gaps (not yet implemented):**
- No formal evaluation harness (fixed set of weekly known events + regression tests)
- No structured logging of searches executed, sources used, and tokens by stage
- No contradiction detection beyond the memory reconciliation step
- No freshness check at parse time (date must be stated in output, but not validated programmatically)

**Cost and scalability:**
- Each scan costs approximately $0.20–$0.50 in API tokens with `claude-sonnet-4-6` (3 competitors, varies with search depth).
- A $2 per-run hard cap is enforced via a mid-stream cost guardrail.
- Running weekly is ~$1–$2/month.

---

## 10. Why Claude API (Not an Off-the-Shelf Tool)

Several SaaS competitive intelligence tools exist (Crayon, Klue, Kompyte). The Claude API approach was chosen because:

1. **Customizable analyst framing.** The system prompt encodes Workday-specific competitive context. Off-the-shelf tools apply generic frameworks.
2. **No vendor lock-in for data.** The agent queries live web sources rather than a vendor's pre-indexed database, which may lag or have coverage gaps.
3. **Full control over evidence standards.** The source quality policy, evidence thresholds, and confidence scoring are configurable. SaaS tools don't expose these knobs.
4. **Full control over output structure and action vocabulary.** The brief format and action catalog are designed for Workday's specific decision workflows.

---

## 11. Example Output Snippet

```
## Step 1 — Search Plan
SAP SuccessFactors | "SAP SuccessFactors product release 2026" | Official newsroom
SAP SuccessFactors | "SAP SuccessFactors AI skills" site:linkedin.com/jobs | Job board
Oracle HCM Cloud   | "Oracle HCM pricing discount 2026" | G2 reviews / press
Rippling           | "Rippling HCM new feature 2026" | Official blog / TechCrunch

## Step 2 — Executive Summary

1. **Rippling launched AI-powered headcount planning** (March 2026, Rippling blog — Tier 1,
   Confidence A). Directly competes with Workday Adaptive Planning in the 100–1,000 employee
   segment. Risk Score: 20 (Impact 5 × Likelihood 4). → ROADMAP_FLAG

2. **Oracle HCM offering 20–25% discounts for SAP migrations** (3 G2 reviews, Q1 2026 —
   Tier 2, Confidence B). Consistent with Oracle's expansion playbook. → PRICING_ALERT

## Step 3 — Competitor Signals

### Rippling
**Signal:** Launched AI-powered headcount planning module
**Date:** March 12, 2026
**Source:** https://rippling.com/blog/... (Tier 1)
**Confidence:** A
**Impact:** 5 — attacks Workday Adaptive Planning in core growth segment
**Likelihood:** 4 — active deals in 500–2,000 employee range
**Time horizon:** NEAR
**Strategic implication:** First feature bringing Rippling into Workday's planning segment
**Recommended action:** ROADMAP_FLAG
**Action owner:** Product Strategy
```
