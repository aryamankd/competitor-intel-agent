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
| ADP Workforce Now | Dominant in payroll; expanding into HCM |
| Ceridian Dayforce | Strong in workforce management and compliance |
| UKG | Competing in scheduling and mid-market HCM |

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
