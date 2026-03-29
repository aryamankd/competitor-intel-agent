# Workday Competitor Intelligence Agent
**Business Foundations AI — Project Submission**

---

## 1. Agent Overview

This agent is a **Competitor Intelligence Analyst** for Workday, a leading provider of enterprise Human Capital Management (HCM) and financial management software. The agent monitors publicly available signals from Workday's key competitors, filters for strategic relevance, and produces a structured one-page intelligence brief for Workday's product, sales, and executive teams.

The agent answers the question: *"What are our competitors doing right now, and what should Workday do about it?"*

---

## 2. Competitor Scope

The agent monitors six primary competitors selected for their direct overlap with Workday's core HCM and payroll market:

| Competitor | Relevance to Workday |
|---|---|
| **SAP SuccessFactors** | Largest direct competitor in enterprise HCM |
| **Oracle HCM Cloud** | Head-to-head in large enterprise and finance |
| **Rippling** | Fast-growing challenger in mid-market HR + IT |
| **ADP Workforce Now** | Dominant in payroll; expanding into HCM |
| **Ceridian Dayforce** | Strong in workforce management and compliance |
| **UKG (Ultimate Kronos Group)** | Competing in scheduling and mid-market HCM |

**Why these six:** They represent Workday's primary deal displacement risk and cover both the enterprise (SAP, Oracle) and the fast-growing challenger segment (Rippling, Ceridian). Companies like BambooHR or Gusto operate in the SMB segment below Workday's typical deal size and are excluded to keep the signal-to-noise ratio high.

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

**Why not real-time or daily:** HCM software moves on product cycles measured in quarters, not hours. Daily scans would surface mostly noise (job postings, minor blog posts) and drive alert fatigue. Weekly scans balance freshness with SNR. Real-time monitoring is reserved for event-triggered runs (e.g., Rippling announces a new funding round or Oracle launches a competing AI feature).

**Why not monthly:** A month is too long in a competitive market. A major product launch or pricing change could go unaddressed for weeks.

---

## 5. Agent Architecture

The agent is built using the **Claude API** (`claude-opus-4-6`) with Anthropic's server-side web search tool. It runs a single agentic loop: Claude autonomously decides what to search, executes those searches on Anthropic's infrastructure, and synthesizes the results into a structured brief.

```
User invokes agent
        │
        ▼
 System prompt (analyst role, Workday context)
 User prompt (competitors, signal categories, output format)
        │
        ▼
 Claude plans searches → executes web_search tool (server-side)
        │   ↑
        │   └── loop until all signals gathered (handles pause_turn)
        ▼
 Claude synthesizes findings → produces structured brief
        │
        ▼
 Brief printed to stdout + saved as JSON
```

**Key design decisions:**

- **Adaptive thinking enabled:** The agent uses `thinking: {"type": "adaptive"}` so Claude reasons carefully about which signals are strategically material vs. noise before writing the brief. This reduces hallucination and improves analytical depth.
- **Server-side web search (not scraping):** The `web_search_20260209` tool runs on Anthropic's infrastructure with dynamic filtering — Claude writes and executes code to filter search results before they consume context window tokens. This keeps the agent efficient and avoids building a scraping pipeline.
- **`pause_turn` handling:** Anthropic's server-side tool loop has a 10-iteration limit per API call. The agent detects `stop_reason == "pause_turn"` and re-sends the conversation to resume, up to a configurable cap.
- **Single-turn structured output:** Rather than multi-turn back-and-forth, the agent produces the full brief in one pass. This keeps latency low and the output format predictable.

---

## 6. Code

```python
# agent.py — core agent logic (simplified for readability)

import anthropic
from datetime import datetime

client = anthropic.Anthropic()
MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """You are a Senior Competitive Intelligence Analyst at Workday.
Monitor competitors in the HCM/ERP space and surface decision-relevant intelligence
for Workday's product, sales, and executive teams. Be specific, cite sources,
and distinguish confirmed signals from inferences."""

def run_intelligence_scan(competitors, focus_areas=None, max_continuations=5):
    messages = [{"role": "user", "content": build_prompt(competitors, focus_areas)}]
    continuations = 0

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "pause_turn":
            # Server-side loop hit iteration cap — re-send to continue
            messages.append({"role": "assistant", "content": response.content})
            continuations += 1
            if continuations >= max_continuations:
                break
            continue
        break  # unexpected stop reason

    return "\n".join(b.text for b in response.content if b.type == "text")
```

The full implementation is in `agent.py`. Run with:

```bash
pip3 install anthropic
export ANTHROPIC_API_KEY=your_key_here
python3 agent.py
```

---

## 7. Output Format

The agent produces a **structured intelligence brief** with four sections:

### Executive Summary
3–5 highest-priority findings that require Workday's attention, written for a C-suite reader who has 60 seconds to scan the page.

### Competitor Signals
For each competitor:
- **Signal** — what specifically changed (with source)
- **Strategic implication** — what it means for Workday
- **Recommended response** — a concrete product, sales, or marketing action

### Risk Radar
Competitive threats to monitor over the next quarter, ranked by urgency.

### Signal Gaps
Where information was sparse. This section prevents false confidence — if Ceridian's pricing page is paywalled, the brief says so rather than staying silent.

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
- **Verify accuracy of claims.** Web search can surface inaccurate or outdated content. Claude is prompted to cite sources, but the output should be treated as a starting point for analyst review, not a ground truth.
- **Predict competitor strategy.** The agent identifies observable signals and draws reasonable inferences, but strategic predictions carry uncertainty. The brief is designed to prompt questions, not answer them definitively.

**Cost and scalability:**
- Each scan costs approximately $0.05–$0.20 in API tokens (varies with response length and search iterations).
- Running weekly for 6 competitors is ~$10/month — well within cost justification for a competitive intelligence function.
- The agent is intentionally scoped to 6 competitors. Expanding to 20+ without a filtering layer would increase cost and degrade output quality as the brief becomes too long to be actionable.

**Hallucination risk:**
- Claude is prompted to cite sources and flag uncertainty, reducing (but not eliminating) fabrication risk. The JSON output preserves the raw brief for audit. In production, a human analyst should spot-check 2–3 claims per brief before distribution.

---

## 9. Why Claude API (Not an Off-the-Shelf Tool)

Several SaaS competitive intelligence tools exist (Crayon, Klue, Kompyte). The Claude API approach was chosen because:

1. **Customizable analyst framing.** The system prompt encodes Workday-specific competitive context (which segments matter, which signals are strategic vs. noise). Off-the-shelf tools apply generic frameworks.
2. **No vendor lock-in for data.** The agent queries live web sources rather than a vendor's pre-indexed database, which may lag or have coverage gaps.
3. **Adaptive reasoning.** Claude's thinking capability lets the agent reason about *why* a signal matters before writing the brief — not just surface-level extraction.
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

🟢 MONITOR: Ceridian's CHRO Summit messaging — early signals of enterprise upmarket push.
```
