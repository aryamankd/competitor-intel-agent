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

MODEL = "claude-opus-4-6"

COMPETITORS = [
    "SAP SuccessFactors",
    "Oracle HCM Cloud",
    "Rippling",
    "ADP Workforce Now",
    "Ceridian Dayforce",
    "UKG (Ultimate Kronos Group)",
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
a leading provider of enterprise HCM and financial management software.

Your job is to monitor competitors in the HCM/ERP space and surface \
decision-relevant intelligence for Workday's product, sales, and executive teams.

When researching competitors, search broadly across:
- Official company newsrooms, blogs, and release notes
- Job boards (LinkedIn, Greenhouse, Lever) for hiring signals
- Press releases and analyst reports (Gartner, IDC, G2)
- Social media and conference announcements
- Partner ecosystem pages

For each signal you find, assess:
1. What specifically changed or was announced?
2. What does this signal strategically — is it a threat, opportunity, or noise?
3. What should Workday's product or go-to-market teams consider in response?

Be specific and cite sources. Distinguish between confirmed facts and inferences.
Prioritize signals from the last 60–90 days. Ignore vague or unsubstantiated claims."""


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
        f"Output: {result['usage']['output_tokens']:,}"
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
    max_continuations: int = 5,
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
    client = anthropic.Anthropic()

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

    user_prompt = f"""Conduct a competitor intelligence scan for Workday as of {current_date}.

Analyze these competitors: {', '.join(competitors)}

Search for recent signals in each of these categories:
{signal_list}{focus_str}{memory_str}

Deliver a structured intelligence brief with these sections:

## Executive Summary
3–5 highest-priority findings that require Workday's attention. Be direct.
{"Lead with what changed since the previous brief." if previous_brief else ""}

## Competitor Signals
For each competitor, list recent signals with:
- Signal (what happened, with source/URL if available)
- Strategic implication for Workday
- Recommended response (product, sales, or marketing action)

## Risk Radar
What competitive threats should Workday monitor closely over the next quarter?

## Signal Gaps
Where was information sparse or unavailable? What should be monitored differently?

Be concise and decision-focused. Avoid filler. Executives will act on this."""

    messages = [{"role": "user", "content": user_prompt}]
    continuations = 0

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
            ],
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "pause_turn":
            # Server-side sampling loop hit its iteration limit.
            # Append the assistant turn and re-send — the API resumes automatically.
            messages.append({"role": "assistant", "content": response.content})
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
        print(
            f"[warn] Unexpected stop_reason: {response.stop_reason}",
            file=sys.stderr,
        )
        break

    final_text = "\n".join(
        block.text for block in response.content if block.type == "text"
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "competitors_analyzed": competitors,
        "focus_areas": focus_areas or [],
        "previous_brief_date": previous_brief.get("generated_at", "")[:10] if previous_brief else None,
        "intelligence_brief": final_text,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
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
        f"Output: {result['usage']['output_tokens']:,}"
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
