# Workday Competitor Intelligence Agent
**Business Foundations AI — Project Submission**

---

## 1. Agent Overview

This agent is a **Competitor Intelligence Analyst** for Workday, a leading provider of enterprise Human Capital Management (HCM) and financial management software. The agent monitors publicly available signals from Workday's key competitors, filters for strategic relevance, and produces a structured intelligence brief for Workday's product, sales, and executive teams.

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

---

## 4. Monitoring Cadence

| Trigger | Frequency | Rationale |
|---|---|---|
| Scheduled scan | Weekly (e.g., every Monday) | Keeps leadership briefed on a predictable cadence |
| Pre-deal research | On-demand | Sales team runs before a competitive deal cycle |
| Event-triggered | After a competitor conference/announcement | Ensures rapid response to major news |

**Why not real-time or daily:** HCM software moves on product cycles measured in quarters, not hours. Daily scans would surface mostly noise and drive alert fatigue. Weekly scans balance freshness with signal-to-noise ratio. Real-time monitoring is reserved for event-triggered runs (e.g., Rippling announces a new funding round or Oracle launches a competing AI feature).

**Why not monthly:** A month is too long in a competitive market. A major product launch or pricing change could go unaddressed for weeks.

---

## 5. Agent Architecture

The agent is built using the **Claude API** (`claude-sonnet-4-6`) with Anthropic's server-side web search tool. It runs a streaming agentic loop: Claude autonomously decides what to search, executes those searches on Anthropic's infrastructure, and synthesizes the results into a structured brief. A real-time cost guardrail monitors token spend mid-stream and cancels the request if the $2 budget is exceeded.

```
User invokes agent
        │
        ▼
 System prompt (analyst role, Workday context)
 User prompt (competitors, signal categories, output format)
 + Previous brief injected if memory file exists (delta analysis)
        │
        ▼
 Claude streams response → web_search tool executes server-side
        │   ↑
        │   └── loop until end_turn or pause_turn (max 2 continuations)
        │         cost guardrail checked on every streaming event
        ▼
 Claude synthesizes findings → structured brief
        │
        ▼
 PDF report + JSON saved to disk
 Memory file updated for next run's delta analysis
```

**Key design decisions:**

- **`claude-sonnet-4-6` over `claude-opus-4-6`:** Sonnet is ~5x cheaper ($3/$15 per million tokens vs $15/$75) with no meaningful quality drop for a search-and-summarize task. Opus's extended reasoning capability is not needed here.
- **No adaptive thinking:** The original implementation used `thinking: {"type": "adaptive"}`, which added significant hidden token spend on internal reasoning before each response. For this use case, it added cost without proportional output quality improvement.
- **Streaming with mid-stream cost cancellation:** Rather than blocking on a single `messages.create()` call (which can hang silently for minutes while the server executes web searches), the agent streams the response. On every `message_start` and `content_block_delta` event, cumulative cost is estimated. If the $2 limit is hit mid-response, the stream is closed and partial results are returned.
- **5-minute hard timeout:** The Anthropic client is initialized with `timeout=300.0` as a safety net in case the stream stalls before the cost guardrail fires.
- **`pause_turn` handling:** Anthropic's server-side tool loop has an iteration limit per API call. The agent detects `stop_reason == "pause_turn"` and re-sends the conversation to resume, capped at 2 continuations to bound cost.
- **Memory / delta tracking:** The previous brief is saved to `last_brief.json`. On the next run, it is injected into the prompt so Claude can classify each signal as NEW, ESCALATING, DE-ESCALATING, or RESOLVED. The executive summary leads with what changed, not just the current state.
- **PDF output:** The brief is rendered as a formatted PDF using `fpdf2`, ready to forward to stakeholders without editing.

---

## 6. Code

```python
# agent.py — core agent logic (simplified for readability)

import anthropic
import sys
from datetime import datetime

MODEL = "claude-sonnet-4-6"
MAX_COST_USD = 2.00
_INPUT_PRICE_PER_M  = 3.00   # claude-sonnet-4-6 pricing
_OUTPUT_PRICE_PER_M = 15.00

def _estimate_cost(input_tokens, output_tokens):
    return (input_tokens / 1_000_000 * _INPUT_PRICE_PER_M
            + output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_M)

SYSTEM_PROMPT = """You are a Senior Competitive Intelligence Analyst at Workday.
Monitor competitors in the HCM/ERP space and surface decision-relevant intelligence
for Workday's product, sales, and executive teams. Be specific, cite sources,
and distinguish confirmed signals from inferences."""

def run_intelligence_scan(competitors, focus_areas=None, previous_brief=None,
                          max_continuations=2):
    client = anthropic.Anthropic(timeout=300.0)  # 5-min hard cap
    messages = [{"role": "user", "content": build_prompt(competitors, focus_areas,
                                                          previous_brief)}]
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
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=messages,
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", None)

                if etype == "message_start":
                    call_input_tokens = event.message.usage.input_tokens
                    if _estimate_cost(total_input_tokens + call_input_tokens,
                                      total_output_tokens) >= MAX_COST_USD:
                        cost_limit_hit = True
                        break

                elif etype == "content_block_delta":
                    chunk = getattr(event.delta, "text", None) or ""
                    accumulated_output_chars += len(chunk)
                    if _estimate_cost(total_input_tokens + call_input_tokens,
                                      total_output_tokens + accumulated_output_chars // 4
                                      ) >= MAX_COST_USD:
                        cost_limit_hit = True
                        break

            if cost_limit_hit:
                snapshot = stream.current_message_snapshot
                content = snapshot.content if snapshot else []
                usage = getattr(snapshot, "usage", None)
                call_output_tokens = usage.output_tokens if usage else accumulated_output_chars // 4
                stop_reason = "cost_limit"
            else:
                msg = stream.get_final_message()
                content = msg.content
                call_input_tokens = msg.usage.input_tokens
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
        break  # unexpected stop reason

    return "\n".join(b.text for b in content if b.type == "text")
```

The full implementation (including PDF rendering, memory/delta tracking, and output saving) is in `agent.py`. Run with:

```bash
pip3 install anthropic fpdf2
export ANTHROPIC_API_KEY=your_key_here
python3 agent.py
```

---

## 7. Output Format

The agent produces a **structured intelligence brief** with four sections, saved as both PDF and JSON:

### Executive Summary
3–5 highest-priority findings that require Workday's attention, written for a C-suite reader who has 60 seconds to scan the page. On subsequent runs, leads with what *changed* since the previous brief.

### Competitor Signals
For each competitor:
- **Signal** — what specifically changed (with source)
- **Strategic implication** — what it means for Workday
- **Recommended response** — a concrete product, sales, or marketing action

Each signal is tagged on delta runs: 🆕 NEW / 📈 ESCALATING / 📉 DE-ESCALATING / ✅ RESOLVED

### Risk Radar
Competitive threats to monitor over the next quarter, ranked by urgency.

### Signal Gaps
Where information was sparse. This section prevents false confidence — if a competitor's pricing page is paywalled, the brief says so rather than staying silent.

**Who reads this:** Workday's VP of Product Strategy, Head of Competitive Intelligence, and regional Sales Directors. The brief is designed to be forwarded without editing.

**What decisions it supports:**
- Product roadmap prioritization (e.g., "Rippling just launched AI-driven org charts — how should we respond?")
- Deal preparation (e.g., "Oracle is discounting 40% for SAP migrations — sales needs updated battlecards")
- Executive positioning (e.g., "SAP SuccessFactors is repositioning around composability — how does Workday's messaging hold up?")

---

## 8. Limitations and Tradeoffs

**What this agent cannot do:**
- **Access paywalled content.** Analyst reports (Gartner Magic Quadrant, IDC MarketScape), private pricing, and internal roadmaps are invisible to web search. The Signal Gaps section surfaces these blind spots explicitly.
- **Monitor in real-time.** This is a batch scan, not a streaming feed. If Rippling announces a major feature at 9am, the agent won't know until the next run.
- **Verify accuracy of claims.** Web search can surface inaccurate or outdated content. Claude is prompted to cite sources, but the output should be treated as a starting point for analyst review, not ground truth.
- **Predict competitor strategy.** The agent identifies observable signals and draws reasonable inferences, but strategic predictions carry uncertainty.

**Cost and scalability:**
- Each scan costs approximately $0.20–$0.50 in API tokens with `claude-sonnet-4-6` (3 competitors, varies with search depth and continuations).
- A $2 per-run hard cap is enforced via a mid-stream cost guardrail — the stream is cancelled if the budget is exceeded, returning partial results rather than an incomplete or missing brief.
- Running weekly is ~$1–$2/month — well within cost justification for a competitive intelligence function.
- Expanding back to 6 competitors without other changes would roughly double token usage and cost.

**Hallucination risk:**
- Claude is prompted to cite sources and flag uncertainty, reducing (but not eliminating) fabrication risk. In production, a human analyst should spot-check 2–3 claims per brief before distribution.

---

## 9. Why Claude API (Not an Off-the-Shelf Tool)

Several SaaS competitive intelligence tools exist (Crayon, Klue, Kompyte). The Claude API approach was chosen because:

1. **Customizable analyst framing.** The system prompt encodes Workday-specific competitive context (which segments matter, which signals are strategic vs. noise). Off-the-shelf tools apply generic frameworks.
2. **No vendor lock-in for data.** The agent queries live web sources rather than a vendor's pre-indexed database, which may lag or have coverage gaps.
3. **Full control over cost.** API pricing is transparent and controllable. The $2 guardrail, model selection, and token limits are configurable in a single config block at the top of `agent.py`.
4. **Full control over output structure.** The brief format is designed for Workday's specific decision workflows, not a generic dashboard.

---

## 10. Example Output Snippet

```
## Executive Summary

1. **Rippling has launched an AI-powered headcount planning module** (announced March 2026),
   directly competing with Workday's Adaptive Planning integration. This is the first major
   feature that brings Rippling into Workday's planning segment.

2. **Oracle HCM dropped pricing by 20–25% for SAP migrations** based on three G2 reviews
   from Q1 2026. This is consistent with Oracle's aggressive expansion playbook and warrants
   updated sales battlecards.

3. **SAP SuccessFactors has 47 open AI/ML engineering roles**, concentrated in skills inference
   and talent marketplace — signaling a 12–18 month product investment cycle in areas where
   Workday Skills Cloud currently leads.

...

## Risk Radar

🔴 HIGH: Rippling's planning module, if priced aggressively, could stall deals in the
         100–1,000 employee segment where Workday's planning upsell is most active.

🟡 MEDIUM: Oracle's migration discounting. Watch for expansion beyond current SAP targets.

🟢 MONITOR: SAP SuccessFactors AI hiring surge — 12–18 month lag before product impact,
            but Skills Cloud differentiation window is narrowing.
```
