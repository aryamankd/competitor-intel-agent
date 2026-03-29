#!/usr/bin/env python3
"""
Workday Competitor Intelligence Agent

Monitors public signals from key Workday competitors and produces
structured, decision-relevant intelligence briefs for Workday leadership.

Competitors monitored: SAP SuccessFactors, Oracle HCM Cloud, Rippling,
                       ADP Workforce Now, Ceridian Dayforce, UKG
Sources: web search across product pages, job boards, press, analyst coverage
Cadence: on-demand (run weekly or event-triggered)
Audience: Workday Product, Sales, and Executive teams
"""

import re
import anthropic
import json
import os
import sys
from datetime import datetime
from fpdf import FPDF

# ─── Configuration ────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"

# Cost guardrail — abort if estimated spend exceeds this during a run
MAX_COST_USD = 2.00

# claude-sonnet-4-6 pricing (per million tokens)
_INPUT_PRICE_PER_M  = 3.00
_OUTPUT_PRICE_PER_M = 15.00


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * _INPUT_PRICE_PER_M
            + output_tokens / 1_000_000 * _OUTPUT_PRICE_PER_M)

COMPETITORS = [
    "SAP SuccessFactors",
    "Oracle HCM Cloud",
    "Rippling",
]

# Signal categories the agent prioritizes when searching
SIGNAL_CATEGORIES = [
    "product launches and feature releases",
    "AI and automation capabilities",
    "hiring patterns and job postings that signal strategic priorities",
    "partnership and integration announcements",
    "pricing or packaging changes",
    "customer wins and analyst coverage",
    "messaging and positioning shifts",
]

SYSTEM_PROMPT = """You are a Senior Competitive Intelligence Analyst at Workday — \
a leading provider of enterprise HCM and financial management software serving \
organizations with 1,000+ employees globally.

## Workday's Core Products (what you are protecting)
- **Workday HCM** — core HR, payroll, talent management, workforce planning
- **Workday Adaptive Planning** — financial and workforce planning/budgeting
- **Workday Financial Management** — accounting, procurement, expenses
- **Workday Skills Cloud** — AI-driven skills ontology and talent intelligence
- **Workday Extend** — platform for custom app development on Workday

## Workday's Competitive Position
**Strengths to defend:** Unified data model (HCM + Finance in one platform), \
enterprise-grade compliance and security, strong customer retention in large enterprise, \
Skills Cloud differentiation in talent intelligence.

**Known vulnerabilities to watch:** Higher total cost of ownership vs. challengers, \
slower implementation timelines, limited mid-market traction (500–2,000 employees), \
UI/UX perception gap vs. newer entrants like Rippling.

## Your Audience
This brief is read by:
- **VP of Product Strategy** — needs to know if a competitor is building into Workday's roadmap
- **Head of Sales Enablement** — needs updated battlecard triggers (pricing moves, new features)
- **Chief People Officer** — needs macro competitive narrative for board and analyst conversations

## Signal Relevance Filter
Only include a signal if it meets at least one of these criteria:
1. It could affect a Workday deal in the next 6 months (pricing, features, positioning)
2. It signals a competitor investing in an area where Workday has a product lead (Skills Cloud, Planning)
3. It represents a new market segment attack (e.g., a mid-market challenger moving upmarket)
4. It changes the competitive narrative Workday uses with analysts or prospects

**Discard:** minor blog posts, generic "AI strategy" announcements without specifics, \
awards, CSR news, and anything without a verifiable source.

## Search Strategy
For each competitor, run 2–3 focused searches in this priority order:
1. Product release notes and feature announcements (last 90 days)
2. Job postings in engineering/product that signal roadmap direction
3. Pricing or packaging changes (G2 reviews, customer forums, sales leaks)
4. Partnership announcements that extend their platform reach

Before executing searches, state your search plan as a brief list: \
`competitor | query | expected source type`. This makes your reasoning inspectable.

## Source Quality Ranking
Rank sources in this order and prefer higher-ranked sources:
1. **Tier 1 (HIGH):** Official newsrooms, product release notes, SEC filings, company blog
2. **Tier 2 (MED):** Reputable press (TechCrunch, WSJ, Bloomberg), G2/Gartner/IDC reports
3. **Tier 3 (LOW):** LinkedIn posts, job boards, forums, social media, anonymous reviews

## Evidence Thresholds
- **High-impact claims** (pricing changes, major product launches, market segment moves): \
require ≥2 independent Tier 1 or Tier 2 sources with publication dates. \
If you cannot meet this threshold, label the signal LOW_EVIDENCE and do not include it \
in the Executive Summary.
- **Supporting signals** (hiring trends, positioning shifts): 1 source acceptable, \
but state the source tier and date explicitly.
- **Insufficient evidence:** If a competitor yields fewer than 2 verifiable signals, \
write "INSUFFICIENT EVIDENCE — [reason]" for that competitor rather than fabricating signals.

## Confidence Scoring
Assign each signal a confidence level:
- **A** — 2+ independent Tier 1/2 sources with dates within 90 days
- **B** — 1 Tier 1/2 source, or 2+ Tier 3 sources with dates
- **C** — single Tier 3 source, or source without a clear publication date

Do not include Confidence C signals in the Executive Summary.

## Output Standards
- Every signal must include: source URL, publication date, source tier, and confidence level
- Distinguish confirmed facts from inferences — label inferences as [INFERRED]
- Be direct — executives will act on this, not read it for interest
- If a signal is ambiguous, say so rather than forcing a conclusion"""


# ─── PDF Report ───────────────────────────────────────────────────────────────

# Emoji → plain-text fallback for PDF (fpdf2 core fonts don't support emoji)
EMOJI_MAP = {
    "🆕": "[NEW]",
    "📈": "[ESCALATING]",
    "📉": "[DE-ESCALATING]",
    "✅": "[RESOLVED]",
    "🔴": "[HIGH]",
    "🟡": "[MEDIUM]",
    "🟢": "[MONITOR]",
}


def _clean(text: str) -> str:
    """Replace emoji with plain-text labels and strip other non-latin chars."""
    for emoji, label in EMOJI_MAP.items():
        text = text.replace(emoji, label)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def save_pdf(result: dict, output_path: str) -> None:
    """
    Render the intelligence brief as a clean PDF report.
    Parses markdown headings (##, ###), bold (**text**), and bullet points.
    """
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # ── Cover header ──────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(0, 84, 166)  # Workday blue
    pdf.cell(0, 10, "Workday Competitor Intelligence Brief", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    gen_date = result.get("generated_at", "")[:10]
    prev_date = result.get("previous_brief_date")
    subtitle = f"Generated: {gen_date}"
    if prev_date:
        subtitle += f"  |  Compared against: {prev_date}"
    pdf.cell(0, 6, subtitle, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Thin rule
    pdf.set_draw_color(0, 84, 166)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    # ── Body ──────────────────────────────────────────────────────────────────
    brief = result.get("intelligence_brief", "")

    for raw_line in brief.splitlines():
        line = _clean(raw_line)

        if line.startswith("## "):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(0, 84, 166)
            pdf.multi_cell(0, 7, line[3:])
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.3)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(3)

        elif line.startswith("### "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 6, line[4:])
            pdf.ln(1)

        elif line.startswith("- ") or line.startswith("* "):
            # Render bold segments inside bullet text
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(40, 40, 40)
            content = line[2:]
            # Strip markdown bold markers for simplicity
            content = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
            pdf.multi_cell(0, 5.5, f"  \u2022  {content}")

        elif line.startswith("---"):
            pdf.ln(2)
            pdf.set_draw_color(220, 220, 220)
            pdf.set_line_width(0.2)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(2)

        elif line.strip() == "":
            pdf.ln(2)

        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(40, 40, 40)
            content = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            pdf.multi_cell(0, 5.5, content)

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_draw_color(0, 84, 166)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    competitors = ", ".join(result.get("competitors_analyzed", []))
    pdf.multi_cell(0, 4, f"Competitors analyzed: {competitors}")
    pdf.multi_cell(
        0, 4,
        f"Tokens used — Input: {result['usage']['input_tokens']:,}  "
        f"Output: {result['usage']['output_tokens']:,}  "
        f"| Estimated cost: ${result['usage']['estimated_cost_usd']:.4f}"
    )
    pdf.multi_cell(0, 4, "Sources: live web search via Anthropic web_search tool. "
                         "Verify critical claims before use in sales or executive contexts.")

    pdf.output(output_path)


# ─── Memory ───────────────────────────────────────────────────────────────────

MEMORY_FILE = "last_brief.json"


def load_previous_brief() -> dict | None:
    """Load the most recent brief from disk, if one exists."""
    if not os.path.exists(MEMORY_FILE):
        return None
    with open(MEMORY_FILE) as f:
        return json.load(f)


def save_as_latest(result: dict) -> None:
    """Overwrite the memory file with the current run's result."""
    with open(MEMORY_FILE, "w") as f:
        json.dump(result, f, indent=2)


# ─── Agent Core ───────────────────────────────────────────────────────────────

def run_intelligence_scan(
    competitors: list[str],
    focus_areas: list[str] | None = None,
    previous_brief: dict | None = None,
    max_continuations: int = 2,
) -> dict:
    """
    Run a competitor intelligence scan using Claude with web search.

    Uses the web_search_20260209 server-side tool, which lets Claude search
    the web autonomously during its response. The agentic loop handles
    pause_turn (server-side sampling limit) by re-sending until end_turn.

    If previous_brief is provided, Claude compares new findings against it
    and flags what's new, escalating, or resolved since the last run.

    Returns a dict with the intelligence brief and usage metadata.
    """
    client = anthropic.Anthropic(timeout=300.0)  # 5-minute hard cap per API call

    current_date = datetime.now().strftime("%B %d, %Y")
    focus_str = (
        f"\n\nFor this scan, pay extra attention to: {', '.join(focus_areas)}"
        if focus_areas
        else ""
    )
    signal_list = "\n".join(f"  - {s}" for s in SIGNAL_CATEGORIES)

    # If we have a previous brief, inject it so Claude can do delta analysis
    memory_str = ""
    if previous_brief:
        prev_date = previous_brief.get("generated_at", "unknown date")[:10]
        prev_text = previous_brief.get("intelligence_brief", "")
        memory_str = f"""

## Previous Brief (from {prev_date})
{prev_text}

---
Compare your new findings against the previous brief above. For each competitor, classify signals as:
- 🆕 NEW — not present in the previous brief
- 📈 ESCALATING — previously noted, now more significant
- 📉 DE-ESCALATING — previously flagged, now less urgent
- ✅ RESOLVED — no longer relevant

In the Executive Summary, lead with what has *changed* since last week, not just the current state."""

    memory_reconciliation = ""
    if previous_brief:
        memory_reconciliation = """
## Step 0 — Memory Reconciliation (do this before searching)
Review the top 3 claims from the previous brief. For each:
- Search to verify it is still accurate and current
- If contradicted by new evidence, mark it RETRACTED with the contradicting source
- If confirmed, carry it forward with CONFIRMED label
Only then proceed to new signal search.
"""

    user_prompt = f"""Conduct a competitor intelligence scan for Workday as of {current_date}.

Analyze these competitors: {', '.join(competitors)}

Search for recent signals in each of these categories:
{signal_list}{focus_str}{memory_reconciliation}{memory_str}

---

## Output Format

### Step 1 — Search Plan
Before executing any searches, list your plan:
`[competitor] | [search query] | [expected source type]`
Limit to 2–3 searches per competitor.

### Step 2 — Executive Summary
{"Lead with what CHANGED since the previous brief." if previous_brief else ""}
3–5 highest-priority findings (Confidence A or B only). Be direct. \
Each finding must reference a source and date.

### Step 3 — Competitor Signals
For each competitor, list signals in this exact format:

**Signal:** [what happened — be specific, not generic]
**Date:** [publication date of source]
**Source:** [URL] (Tier [1/2/3])
**Confidence:** [A / B / C]
{"**Delta:** [🆕 NEW / 📈 ESCALATING / 📉 DE-ESCALATING / ✅ RESOLVED]" if previous_brief else ""}
**Impact on Workday (1–5):** [score] — [one-line reason]
**Likelihood of materially affecting a deal (1–5):** [score]
**Time horizon:** [NEAR <3mo / MID 3–9mo / LONG 9mo+]
**Strategic implication:** [what this means for Workday's position]
**Recommended action:** [exactly one of: BATTLECARD_UPDATE / ROADMAP_FLAG / PRICING_ALERT / PARTNER_WATCH / MONITOR]
**Action owner:** [Sales Enablement / Product Strategy / Executive / Marketing]

If evidence is insufficient for a competitor, write:
`INSUFFICIENT EVIDENCE — [reason, e.g., no public announcements in 90 days]`

### Step 4 — Risk Radar
Rank the top threats using this model:
`Risk score = Impact × Likelihood` (both 1–5)
For each risk: state score, time horizon, and what would accelerate it.

### Step 5 — Signal Gaps
Where was evidence sparse, paywalled, or below the evidence threshold?
What search approach would improve coverage next run?

Be concise and decision-focused. Avoid filler. Executives will act on this."""

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
                    cost = _estimate_cost(
                        total_input_tokens + call_input_tokens,
                        total_output_tokens,
                    )
                    if cost >= MAX_COST_USD:
                        cost_limit_hit = True
                        break

                elif etype == "content_block_delta":
                    delta = event.delta
                    chunk = getattr(delta, "text", None) or ""
                    accumulated_output_chars += len(chunk)
                    cost = _estimate_cost(
                        total_input_tokens + call_input_tokens,
                        total_output_tokens + accumulated_output_chars // 4,
                    )
                    if cost >= MAX_COST_USD:
                        cost_limit_hit = True
                        break

            if cost_limit_hit:
                snapshot = stream.current_message_snapshot
                content = snapshot.content if snapshot else []
                usage = getattr(snapshot, "usage", None)
                call_input_tokens = usage.input_tokens if usage else call_input_tokens
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
        estimated_cost = _estimate_cost(total_input_tokens, total_output_tokens)

        print(
            f"  [cost] ~${estimated_cost:.3f} so far "
            f"({total_input_tokens:,} in / {total_output_tokens:,} out)",
            file=sys.stderr,
        )

        if stop_reason == "cost_limit":
            print(
                f"[guardrail] Cost limit ${MAX_COST_USD:.2f} hit mid-response. "
                "Stopped stream and using partial results.",
                file=sys.stderr,
            )
            break

        if stop_reason == "end_turn":
            break

        if stop_reason == "pause_turn":
            # Server-side sampling loop hit its iteration limit.
            # Append the assistant turn and re-send — the API resumes automatically.
            messages.append({"role": "assistant", "content": content})
            continuations += 1
            if continuations >= max_continuations:
                print(
                    f"[warn] Reached max continuations ({max_continuations}). "
                    "Using partial results.",
                    file=sys.stderr,
                )
                break
            continue

        # Unexpected stop reason — exit loop
        print(f"[warn] Unexpected stop_reason: {stop_reason}", file=sys.stderr)
        break

    final_text = "\n".join(
        block.text for block in content if block.type == "text"
    )

    # ── Output completeness validation ────────────────────────────────────────
    required_sections = [
        "Executive Summary",
        "Competitor Signals",
        "Risk Radar",
        "Signal Gaps",
    ]
    missing = [s for s in required_sections if s not in final_text]
    if missing:
        print(
            f"[warn] Output missing sections: {', '.join(missing)}. "
            "Brief may be partial due to cost guardrail or early termination.",
            file=sys.stderr,
        )

    for competitor in competitors:
        name = competitor.split(" ")[0]  # e.g. "SAP" from "SAP SuccessFactors"
        if name not in final_text:
            print(
                f"[warn] No signals found for {competitor} in output.",
                file=sys.stderr,
            )

    return {
        "generated_at": datetime.now().isoformat(),
        "competitors_analyzed": competitors,
        "focus_areas": focus_areas or [],
        "previous_brief_date": previous_brief.get("generated_at", "")[:10] if previous_brief else None,
        "intelligence_brief": final_text,
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost_usd": round(_estimate_cost(total_input_tokens, total_output_tokens), 4),
        },
    }


# ─── Entrypoint ───────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("  WORKDAY COMPETITOR INTELLIGENCE AGENT")
    print(f"  Scan initiated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 64)
    print(f"\nMonitoring {len(COMPETITORS)} competitors:")
    for c in COMPETITORS:
        print(f"  · {c}")

    # Load memory from previous run
    previous = load_previous_brief()
    if previous:
        prev_date = previous.get("generated_at", "")[:10]
        print(f"\nMemory: previous brief found from {prev_date} — delta analysis enabled")
    else:
        print("\nMemory: no previous brief found — running full baseline scan")

    print("\nSearching across: product news, job boards, press, analyst coverage")
    print("This may take 2–5 minutes (multiple live web searches across 6 competitors)...\n")

    result = run_intelligence_scan(
        competitors=COMPETITORS,
        focus_areas=[
            "AI/ML features and automation roadmap",
            "SMB and mid-market expansion",
            "skills and talent intelligence products",
        ],
        previous_brief=previous,
    )

    print("\n" + "=" * 64)
    print("  INTELLIGENCE BRIEF")
    print("=" * 64 + "\n")
    print(result["intelligence_brief"])

    print("\n" + "─" * 64)
    print(
        f"Tokens — Input: {result['usage']['input_tokens']:,}  "
        f"Output: {result['usage']['output_tokens']:,}  "
        f"| Estimated cost: ${result['usage']['estimated_cost_usd']:.4f}"
    )

    # Save timestamped archive copies (JSON + PDF)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = f"intel_brief_{timestamp}.json"
    pdf_path = f"intel_brief_{timestamp}.pdf"

    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"JSON saved  → {json_path}")

    save_pdf(result, pdf_path)
    print(f"PDF saved   → {pdf_path}")

    # Update memory for next run
    save_as_latest(result)
    print(f"Memory updated → {MEMORY_FILE}")


if __name__ == "__main__":
    main()
