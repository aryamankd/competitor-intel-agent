# Workday Competitor Intelligence Agent

An AI agent that monitors public signals from Workday's key competitors and produces structured, decision-relevant intelligence briefs — automatically, every week.

Built with the Claude API (`claude-opus-4-6`) and Anthropic's server-side web search tool.

---

## What It Does

You run it. It searches the web across product pages, job boards, press releases, and analyst coverage for six of Workday's key competitors. Claude reasons about what's strategically relevant, compares findings against the previous week's brief, and produces a formatted report as both a **PDF** and **JSON**.

**Output looks like this:**

```
## Executive Summary
1. 🆕 Rippling launched AI-powered headcount planning — directly competing with
   Workday Adaptive Planning in the 100–1,000 employee segment.
2. 📈 Oracle HCM is offering 20–25% discounts for SAP migrations (3 G2 reviews, Q1 2026).
3. 🆕 SAP SuccessFactors has 47 open AI/ML roles — signaling a 12–18 month
   product investment in skills inference.
```

---

## Competitors Monitored

| Competitor | Why It's Included |
|---|---|
| SAP SuccessFactors | Largest direct competitor in enterprise HCM |
| Oracle HCM Cloud | Head-to-head in large enterprise and finance |
| Rippling | Fast-growing challenger in mid-market HR + IT |

**Why three instead of six:** Each competitor triggers multiple server-side web searches (product news, job boards, press, analyst coverage). With 6 competitors and 7 signal categories, a single run executes 40+ searches, flooding the context window with search results. When `pause_turn` continuations occur, that entire history is re-sent as input tokens — causing costs to exceed $2 per run. Reducing to 3 competitors cuts search volume roughly in half and keeps runs well within budget. ADP Workforce Now, Ceridian Dayforce, and UKG can be added back via `COMPETITORS` in `agent.py` if needed.

---

## How Signals Are Sourced

The agent uses **Anthropic's server-side web search tool** (`web_search_20260209`). There are no external APIs, scrapers, or pre-indexed databases involved.

When the agent runs, Claude is given the web search tool and autonomously:
1. Decides what queries to run based on the competitors and signal categories in the prompt
2. Executes those searches on Anthropic's infrastructure
3. Filters and reads the results within its context window
4. Synthesizes findings into the structured brief

Because searches happen at runtime against live web sources, the brief reflects current information — not a snapshot from a vendor's database that may be weeks or months stale.

**What it can reach:** Public web — company newsrooms, product blogs, job boards (LinkedIn, Greenhouse, Lever), press releases, G2/Gartner reviews, conference announcements, partner pages.

**What it cannot reach:** Paywalled content (Gartner Magic Quadrant full reports, private pricing, LinkedIn Sales Navigator). The `Signal Gaps` section of every brief flags where coverage was limited.

---

## Signal Categories

The agent searches for signals across:
- Product launches and feature releases
- AI and automation capabilities
- Hiring patterns that signal strategic direction
- Partnership and integration announcements
- Pricing or packaging changes
- Customer wins and analyst coverage
- Messaging and positioning shifts

Signals are filtered before inclusion — only surfaced if they could affect a Workday deal in the next 6 months, attack an area where Workday has a product lead, or change the competitive narrative with analysts or prospects. Minor blog posts, generic "AI strategy" announcements, awards, and CSR news are discarded.

---

## System Prompt Design

The system prompt encodes Workday-specific context so Claude reasons like an internal analyst, not a generic summarizer:

**Workday's core products** (HCM, Adaptive Planning, Financial Management, Skills Cloud, Extend) are listed explicitly so Claude knows what's at risk when a competitor makes a move.

**Competitive position** — Workday's strengths (unified data model, Skills Cloud lead, enterprise retention) and known vulnerabilities (TCO, mid-market traction, UX perception gap) are documented. This lets Claude assess signal severity: an attack on a known weak spot is flagged differently from a move into a segment Workday dominates.

**Audience definitions** — the brief is framed for three readers: VP of Product Strategy (roadmap threats), Head of Sales Enablement (battlecard triggers), and Chief People Officer (board narrative). Claude writes for the person who will act on each finding.

**Search strategy** — Claude is instructed to run 2–3 targeted searches per competitor rather than exhaustive coverage. This directly reduces web search volume, context window usage, and cost.

---

## Memory / Delta Tracking

The agent remembers the previous run. On the second run onward, each signal is classified as:

- 🆕 **NEW** — not present in the previous brief
- 📈 **ESCALATING** — previously noted, now more significant
- 📉 **DE-ESCALATING** — previously flagged, now less urgent
- ✅ **RESOLVED** — no longer relevant

The Executive Summary leads with *what changed*, not just the current state. This turns a weekly snapshot into a trend tracker.

---

## Setup

**Requirements:** Python 3.11+, an Anthropic API key (~$0.10–$0.15 per run)

```bash
git clone <this-repo>
cd competitor-intel-agent

pip3 install -r requirements.txt

export ANTHROPIC_API_KEY=your_key_here
# Get a key at: console.anthropic.com
```

---

## Running the Agent

```bash
python3 agent.py
```

**Runtime:** Expect 2–5 minutes per run. The agent executes 20–40+ live web searches across 6 competitors and multiple signal categories, with each search being a round-trip to Anthropic's servers. Claude may also re-send the conversation multiple times if the server-side search iteration limit is hit.

**First run:** Full baseline scan. Saves `last_brief.json` as memory for next run.

**Subsequent runs:** Delta analysis — compares against previous brief and flags what changed.

**Output files:**
- `intel_brief_YYYYMMDD_HHMM.pdf` — formatted report, ready to share
- `intel_brief_YYYYMMDD_HHMM.json` — raw data for downstream use
- `last_brief.json` — memory file used for delta comparison next run

---

## Recommended Cadence

| Mode | How |
|---|---|
| **Weekly scan** | Add a cron job: `0 9 * * 1 cd /path/to/agent && python3 agent.py` |
| **Pre-deal research** | Run on-demand before a competitive sales cycle |
| **Event-triggered** | Run manually after a major competitor announcement |

---

## Customizing

All configuration is at the top of `agent.py`:

```python
COMPETITORS = [...]          # Add or remove competitors
SIGNAL_CATEGORIES = [...]    # Adjust signal priorities
focus_areas = [...]          # In main(), steer attention for a given run
```

---

## Architecture

```
You run agent.py
      │
      ▼
System prompt (Workday analyst role + context)
User prompt (competitors, signal categories, output format)
+ Previous brief injected if memory exists
      │
      ▼
Claude plans searches → executes web_search tool (server-side, Anthropic infra)
      │   ↑
      └───┘ loop (handles pause_turn for long searches)
      │
      ▼
Claude synthesizes → structured intelligence brief
      │
      ▼
PDF report + JSON saved, memory updated
```

**Why Claude API instead of a SaaS tool (Crayon, Klue):**
- Workday-specific analyst framing via system prompt
- Queries live web sources, not a vendor's pre-indexed database
- Adaptive reasoning about what's strategically relevant (not just extraction)
- Full control over output format and decision framing

---

## Limitations

- **No paywalled content.** Gartner reports, private pricing, LinkedIn Sales Navigator are invisible. The `Signal Gaps` section in every brief flags this explicitly.
- **Not real-time.** Point-in-time snapshot per run, not a live feed.
- **Hallucination risk.** Claude is prompted to cite sources, but outputs should be treated as analyst starting points, not ground truth. Spot-check 2–3 claims per brief.
- **Memory is local.** `last_brief.json` lives on disk — no database. For a multi-user deployment, this would need to move to shared storage.

---

## Cost

~$0.10–$0.15 per run in Anthropic API tokens. Weekly cadence = ~$0.50–$0.60/month.

Monitor usage at [console.anthropic.com](https://console.anthropic.com).
