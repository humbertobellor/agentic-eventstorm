"""
synthesis.py — DDD Artifact Generator
========================================
At the close of Phase 8, the Facilitator produces a complete set of
Domain-Driven Design artifacts from the board state. These artifacts are
the primary deliverable of the entire workshop.

This module handles both the Claude-driven narrative synthesis (which
produces prose summaries and design recommendations) and the structured
text artifact generation (which produces tables and formatted reference
documents).
"""

import anthropic
from board import BoardState


# ─────────────────────────────────────────────────────────────────────────────
# Structured Artifact Builders  (deterministic, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def build_domain_event_catalog(board: BoardState) -> str:
    """Produces a formatted Domain Event Catalog table."""
    lines = [
        "## Domain Event Catalog",
        "",
        f"Total domain events discovered: {len(board.domain_events)}",
        f"Pivotal events: {', '.join(board.pivotal_events) if board.pivotal_events else 'None marked'}",
        "",
        f"{'Event Name':<40} {'Aggregate':<25} {'Bounded Context':<35} {'Originating Agent':<20}",
        "─" * 120,
    ]
    for e in board.domain_events:
        pivotal = "★ " if e.is_pivotal else "  "
        lines.append(
            f"{pivotal}{e.name:<38} "
            f"{(e.aggregate or '—'):<25} "
            f"{(e.bounded_context or '— unassigned —'):<35} "
            f"{e.originating_agent:<20}"
        )
    return "\n".join(lines)


def build_command_catalog(board: BoardState) -> str:
    """Produces a formatted Command Catalog table."""
    lines = [
        "## Command Catalog",
        "",
        f"Total commands identified: {len(board.commands)}",
        "",
        f"{'Command Name':<35} {'Triggers Event':<35} {'Actor':<25} {'Read Model Required':<30}",
        "─" * 125,
    ]
    # Build a lookup from command name to read model
    read_model_by_cmd = {r.required_before_command: r.name for r in board.read_models}
    for c in board.commands:
        rm = read_model_by_cmd.get(c.name, "—")
        lines.append(
            f"{c.name:<35} {c.triggers_event:<35} {c.actor:<25} {rm:<30}"
        )
    return "\n".join(lines)


def build_aggregate_definitions(board: BoardState) -> str:
    """Produces detailed Aggregate Definition blocks."""
    lines = [
        "## Aggregate Definitions",
        "",
        f"Total aggregates defined: {len(board.aggregates)}",
        "",
    ]
    for agg in board.aggregates:
        lines.extend([
            f"### Aggregate: {agg.name}",
            f"Bounded Context: {agg.bounded_context or '— unassigned —'}",
            "",
            f"Commands received ({len(agg.related_commands)}):",
            *[f"  • {cmd}" for cmd in agg.related_commands],
            "",
            f"Events produced ({len(agg.related_events)}):",
            *[f"  • {evt}" for evt in agg.related_events],
            "",
            f"Invariants ({len(agg.invariants)}):",
            *([f"  • {inv}" for inv in agg.invariants] if agg.invariants else ["  — None defined (flag for follow-up)"]),
            "",
            "─" * 60,
            "",
        ])
    return "\n".join(lines)


def build_policy_register(board: BoardState) -> str:
    """Produces a Policy Register table."""
    lines = [
        "## Policy Register",
        "",
        f"Total policies defined: {len(board.policies)}",
        cross := sum(1 for p in board.policies if p.crosses_context_boundary),
        f"Cross-context policies (integration points): {cross}",
        "",
        f"{'Triggered By Event':<35} {'Triggers Command':<35} {'Crosses Context':<15} {'Rule Description'}",
        "─" * 130,
    ]
    # Remove the integer that snuck in from the walrus assignment
    lines = [l for l in lines if not isinstance(l, int)]
    for p in board.policies:
        cross_flag = "⚡ YES" if p.crosses_context_boundary else "No"
        rule_preview = p.rule_description[:50] + ("..." if len(p.rule_description) > 50 else "")
        lines.append(
            f"{p.triggered_by_event:<35} {p.triggers_command:<35} {cross_flag:<15} {rule_preview}"
        )
    return "\n".join(lines)


def build_bounded_context_map(board: BoardState) -> str:
    """Produces a text-diagram Bounded Context Map."""
    lines = [
        "## Bounded Context Map",
        "",
        f"Total bounded contexts: {len(board.bounded_contexts)}",
        "",
    ]
    for bc in board.bounded_contexts:
        lines.extend([
            f"┌─ [{bc.name}]",
            f"│  Aggregates: {', '.join(bc.aggregates) if bc.aggregates else '— none assigned'}",
            f"│  Relationship type: {bc.relationship_type or '— unspecified'}",
        ])
        if bc.upstream_contexts:
            for up in bc.upstream_contexts:
                lines.append(f"│  UPSTREAM ← [{up}]")
        if bc.downstream_contexts:
            for down in bc.downstream_contexts:
                rel = f"  (via {bc.relationship_type})" if bc.relationship_type else ""
                lines.append(f"│  DOWNSTREAM → [{down}]{rel}")
        if bc.integration_events:
            lines.append(f"│  Integration events: {', '.join(bc.integration_events)}")
        lines.append("└─")
        lines.append("")
    return "\n".join(lines)


def build_hotspot_resolution_log(board: BoardState) -> str:
    """Produces a Hot Spot Resolution Log."""
    open_hs   = [h for h in board.hotspots if not h.resolved]
    closed_hs = [h for h in board.hotspots if h.resolved]

    lines = [
        "## Hot Spot Resolution Log",
        "",
        f"Total hot spots: {len(board.hotspots)} "
        f"| Resolved: {len(closed_hs)} | Open: {len(open_hs)}",
        "",
    ]
    if open_hs:
        lines.extend(["### OPEN Hot Spots (require follow-up)", ""])
        for h in open_hs:
            lines.extend([
                f"  [{h.severity}] {h.type.upper()}: {h.description}",
                f"  Flagged by: {h.flagged_by or '—'}",
                f"  Related events: {', '.join(h.related_events) or '—'}",
                "",
            ])
    if closed_hs:
        lines.extend(["### RESOLVED Hot Spots", ""])
        for h in closed_hs:
            lines.extend([
                f"  ✓ [{h.severity}] {h.type.upper()}: {h.description}",
                f"  Resolution: {h.resolution or '— (implicit resolution)'}",
                f"  {('Dissent recorded: ' + h.dissenting_view) if h.dissenting_view else ''}",
                "",
            ])
    return "\n".join(lines)


def build_open_assumptions_log(board: BoardState) -> str:
    """Produces the Open Assumptions and Deferred Decisions log."""
    lines = [
        "## Open Assumptions and Deferred Decisions",
        "",
        "The following items were surfaced during the workshop but not fully resolved.",
        "Each requires a named owner and a next action before implementation begins.",
        "",
    ]
    deferred = [h for h in board.hotspots if not h.resolved and h.severity in ("Medium", "Low")]
    if deferred:
        for i, h in enumerate(deferred, 1):
            lines.extend([
                f"{i}. [{h.severity}] {h.description}",
                f"   Type: {h.type} | Flagged by: {h.flagged_by or 'unknown'}",
                f"   Suggested next action: Assign to domain expert for validation before Sprint 1.",
                "",
            ])
    else:
        lines.append("No deferred items. All hot spots were resolved during the workshop.")

    if board.facilitator_notes:
        lines.extend(["", "### Facilitator Notes", ""])
        for note in board.facilitator_notes:
            lines.append(f"  📋 {note}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# LLM-Powered Narrative Synthesis
# ─────────────────────────────────────────────────────────────────────────────

def run_narrative_synthesis(
    board: BoardState,
    client: anthropic.Anthropic,
    model: str = "claude-opus-4-5",
) -> str:
    """
    Ask the Facilitator agent (as Claude Opus) to produce a prose narrative
    of the domain model — the kind of summary a lead architect would write
    at the top of the design document to orient new team members.
    """
    board_summary = board.to_context_summary()

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=(
            "You are the EventStorming Facilitator writing the final design narrative "
            "for a software team who will implement this domain model. "
            "Write in clear, confident prose. Do not use bullet points. "
            "Do not invent any domain elements not present in the board state. "
            "Label any inference or recommendation as [Recommendation]."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Based on the completed EventStorming board below, write a "
                f"Domain Design Narrative of approximately 400 words that:\n"
                f"1. Summarizes the domain and its primary business purpose.\n"
                f"2. Describes the core bounded contexts and their responsibilities.\n"
                f"3. Explains the most important integration patterns between contexts.\n"
                f"4. Highlights any design decisions that require careful implementation attention.\n"
                f"5. Notes the most critical business invariants to enforce.\n\n"
                f"{board_summary}"
            ),
        }],
    )

    return response.content[0].text if response.content else ""


# ─────────────────────────────────────────────────────────────────────────────
# Complete Artifact Assembly
# ─────────────────────────────────────────────────────────────────────────────

def generate_all_artifacts(
    board: BoardState,
    client: anthropic.Anthropic,
    include_narrative: bool = True,
) -> str:
    """
    Assemble the complete DDD artifact set as a single Markdown document.
    This is the primary deliverable of the entire workshop.
    """
    sections = [
        f"# EventStorming Workshop — DDD Artifact Report",
        f"",
        f"**Domain:** {board.domain}",
        f"**Scope:** {board.scope}",
        f"**Timeline:** [{board.start_event}] → [{board.end_event}]",
        f"**Workshop phases completed:** {board.current_phase}",
        f"",
        "---",
        "",
    ]

    if include_narrative:
        sections.extend([
            "## Domain Design Narrative",
            "",
            run_narrative_synthesis(board, client),
            "",
            "---",
            "",
        ])

    sections.extend([
        build_domain_event_catalog(board), "", "---", "",
        build_command_catalog(board),      "", "---", "",
        build_aggregate_definitions(board),"", "---", "",
        build_policy_register(board),      "", "---", "",
        build_bounded_context_map(board),  "", "---", "",
        build_hotspot_resolution_log(board), "", "---", "",
        build_open_assumptions_log(board), "",
    ])

    return "\n".join(sections)
