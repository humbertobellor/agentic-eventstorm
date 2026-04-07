"""
agents.py — Participant Agent Definitions and Runner
======================================================
Each of the six participant agents is defined as a configuration dict that
specifies their role, professional backstory, domain lens, and the phases in
which they contribute most heavily.

The run_participant_agent() function executes a full Claude tool-use loop
for one agent in one phase: Claude reasons about what to contribute, calls
board tools, receives results, and repeats until it has no more contributions
to make. All mutations land on the shared BoardState object.
"""

import anthropic
from board import BoardState
from tools import TOOL_SCHEMAS, handle_tool_call


# ─────────────────────────────────────────────────────────────────────────────
# Participant Agent Definitions
# ─────────────────────────────────────────────────────────────────────────────

PARTICIPANT_AGENTS = {
    "CEO": {
        "role": "Chief Executive Officer",
        "backstory": (
            "Fifteen years of agency leadership with deep expertise in client retention, "
            "account growth, and strategic risk. You have signed hundreds of client contracts "
            "and have a sharp eye for where business value is created or destroyed. "
            "You think in terms of outcomes, relationships, and organizational risk."
        ),
        "lens": "business outcomes, client relationships, strategic risk, investment decisions",
        "contributes": (
            "Pivotal business events, strategic policies, cross-functional dependencies, "
            "client-facing milestones, budget and contract events."
        ),
        "primary_phases": [1, 2, 6, 7],   # event discovery, narrative, contexts, hot spots
    },
    "CMO": {
        "role": "Chief Marketing Officer",
        "backstory": (
            "Former brand strategist with twelve years of experience across performance "
            "marketing and creative direction. You have led dozens of campaign launches "
            "and understand the full marketing funnel from awareness through conversion. "
            "You think in terms of customer journeys, brand consistency, and campaign ROI."
        ),
        "lens": "customer journey, brand, campaign strategy, audience segmentation",
        "contributes": (
            "Customer-facing events, campaign approval and launch events, "
            "audience segmentation policies, creative direction milestones, campaign lifecycle states."
        ),
        "primary_phases": [1, 2, 4, 5, 6],
    },
    "MARKETER": {
        "role": "Marketing Specialist",
        "backstory": (
            "Hands-on campaign manager with eight years of execution experience across "
            "paid search, social media, email, and content marketing. "
            "You know the operational realities of running campaigns at scale: the tools, "
            "the workflows, the things that go wrong on launch day. "
            "You think in terms of channels, deliverables, and execution timelines."
        ),
        "lens": "channel execution, content operations, campaign tooling, day-to-day workflows",
        "contributes": (
            "Operational events, channel-specific commands, content lifecycle events, "
            "A/B test events, audience segmentation commands, publishing workflows."
        ),
        "primary_phases": [1, 3, 4],
    },
    "ANALYST": {
        "role": "Research Analyst",
        "backstory": (
            "Former data scientist now specializing in marketing analytics and business intelligence. "
            "Six years of experience building attribution models, anomaly detection pipelines, "
            "and executive dashboards. You have strong opinions about data quality and what "
            "it means for a metric to actually be trustworthy. "
            "You think in terms of measurement, attribution, and insight validity."
        ),
        "lens": "data quality, measurement frameworks, attribution, anomaly detection",
        "contributes": (
            "Measurement events, reporting commands, anomaly detection events, "
            "data quality hot spots, read models (dashboards and reports), attribution policies."
        ),
        "primary_phases": [1, 3, 4, 7],
    },
    "ENGINEER": {
        "role": "Software Engineer",
        "backstory": (
            "Full-stack engineer with ten years of experience building campaign management "
            "platforms, ad tech integrations, and marketing data pipelines. "
            "You have been paged at 2am because a tracking pixel stopped firing, "
            "and you have strong views about system boundaries and failure modes. "
            "You think in terms of APIs, reliability, consistency, and what can go wrong."
        ),
        "lens": "systems, APIs, reliability, external integrations, technical failure modes",
        "contributes": (
            "Integration events, technical commands, external system definitions, "
            "failure-mode hot spots, aggregate boundaries, API contract events."
        ),
        "primary_phases": [1, 3, 5, 6],
    },
    "PM": {
        "role": "Product Manager",
        "backstory": (
            "Product manager with seven years of experience shipping agency workflow tools "
            "and client-facing campaign products. You have written hundreds of user stories "
            "and sat through every kind of sprint review. "
            "You understand how feature decisions create or eliminate domain complexity. "
            "You think in terms of user goals, delivery milestones, and product lifecycle."
        ),
        "lens": "user stories, feature lifecycle, roadmap decisions, delivery milestones",
        "contributes": (
            "Feature lifecycle events, acceptance policies, release milestone events, "
            "product decision hot spots, aggregate lifecycle definitions."
        ),
        "primary_phases": [1, 4, 5, 7],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Phase-Specific Prompt Templates
# ─────────────────────────────────────────────────────────────────────────────

PHASE_PROMPTS = {
    1: """
WORKSHOP PHASE 1 — Chaotic Domain Event Discovery

Your job right now is to contribute as many domain events as you can from your perspective.

RULES FOR THIS PHASE:
• Write every event in past tense: "Campaign Published", "Order Shipped", "Contract Signed".
• Do NOT filter or self-censor. Quantity matters more than quality at this stage.
• Do NOT critique other agents' events — that happens in Phase 2.
• Include failure events, exception paths, and edge cases.
• Do NOT add commands, policies, or aggregates yet — events only.

Start by calling get_board_state() to see what has already been placed.
Then use add_domain_event() repeatedly to place your events.
Aim for at least 5–8 events from your domain lens.
When you have placed all your events, stop making tool calls.
""",
    2: """
WORKSHOP PHASE 2 — Timeline Ordering and Narrative Walk

The board now has a raw collection of events. Your job is to:
1. Call get_board_state() to review all events.
2. Identify any events from your domain lens that appear out of sequence — describe
   where they should sit relative to other events (early/mid/late in the timeline).
3. Identify any PIVOTAL EVENTS from your perspective — events that clearly mark the
   transition from one major business phase to another.
4. Flag any event that appears to duplicate another but may mean something different
   to your team — use mark_hotspot() with type="conflict".
5. Flag any obvious gap in the timeline from your domain lens — use mark_hotspot()
   with type="question".

Do NOT add new events unless you identify a critical gap.
""",
    3: """
WORKSHOP PHASE 3 — Commands, Actors, and External Systems

For each domain event that falls within your domain lens, contribute the following:
1. The COMMAND that caused the event — use add_command(). Write it in the imperative:
   "Publish Campaign" causes "Campaign Published".
2. The ACTOR who issued the command — a role, not an individual name.
3. Any EXTERNAL SYSTEM involved — use add_external_system() for any third-party
   service that either receives or emits events at the boundary of your domain.

Call get_board_state(filter_by="domain_events") first to see which events need commands.
Flag any event with no clear command owner using mark_hotspot(type="question").
""",
    4: """
WORKSHOP PHASE 4 — Policies and Read Models

Two contributions are needed from you in this phase:

1. POLICIES: For any domain event in your area that automatically triggers another
   action, use add_policy() to capture the reactive rule:
   "Whenever [Event], then [Command]."
   Set crosses_context_boundary=True if the event and its consequence belong to
   different business areas.

2. READ MODELS: For any command in your area, identify what information the actor
   must see BEFORE issuing that command. Use add_read_model() to place it.
   Example: Before "Pause Campaign", a Marketer needs to see a "Campaign Performance Dashboard".

Call get_board_state(filter_by="commands") to see which commands might need read models.
""",
    5: """
WORKSHOP PHASE 5 — Aggregate Identification

Your task is to cluster related events and commands around natural business entities.

An AGGREGATE is a cluster of domain objects that:
• Share a common lifecycle (they are created, modified, and closed together).
• Enforce a consistent set of business rules.
• Are named with a single business noun: "Campaign", "Order", "Customer Account".

Use define_aggregate() to name and group related events and commands.
For each aggregate, define at least one INVARIANT — a business rule that must
always hold true, e.g. "A campaign cannot be published without an approved audience segment."

CRITICAL: After naming each aggregate, ask yourself — is this the word the business
actually uses in daily conversation? If your CMO would not use this word in a client
meeting, it is wrong. Flag the discrepancy with mark_hotspot(type="conflict").

Call get_board_state(filter_by="domain_events") first to review what needs grouping.
""",
    6: """
WORKSHOP PHASE 6 — Bounded Context Definition

You are now contributing to the most architecturally significant phase of the workshop.

A BOUNDED CONTEXT is a boundary of consistent language and shared meaning.
Inside the boundary, a term like "Campaign" means exactly one thing.
Across the boundary, the same word may mean something completely different — and that
difference is the boundary.

Your contribution:
1. Call get_board_state() to review all aggregates and pivotal events.
2. Propose at least one bounded context from your domain lens — name it after
   the vocabulary used inside it.
3. Use define_bounded_context() and specify:
   • Which aggregates belong inside.
   • Which contexts are upstream (provide data to this one).
   • Which contexts are downstream (consume data from this one).
   • The relationship type: Customer-Supplier, Published Language, Shared Kernel,
     Anti-Corruption Layer, or Conformist.
4. If you disagree with another agent's context boundary, flag it as a
   mark_hotspot(type="conflict", severity="High").
""",
    7: """
WORKSHOP PHASE 7 — Hot Spot Resolution

The workshop is nearly complete. Your task is to resolve or escalate every
open Hot Spot that falls within your domain lens.

Call get_board_state(filter_by="hotspots") first.

For each open Hot Spot you can address:
• If it is a QUESTION you can answer — state the answer clearly.
• If it is a CONFLICT you have a view on — state your position in one sentence.
  The Facilitator will synthesize. Do NOT simply agree to avoid conflict —
  your dissenting view is valuable and will be recorded.
• If it is a RISK or COMPLEXITY — assess the impact and suggest a mitigation.

You do not need to resolve every hot spot — only the ones within your expertise.
Flag any new hot spots that have become visible during your review.
""",
}


# ─────────────────────────────────────────────────────────────────────────────
# Participant Agent Tools  (a restricted subset for domain experts)
# ─────────────────────────────────────────────────────────────────────────────

# Participant agents do not get advance_workshop_phase — only the Facilitator does.
PARTICIPANT_TOOL_NAMES = {
    "add_domain_event", "add_command", "add_read_model", "add_external_system",
    "add_policy", "mark_hotspot", "define_aggregate", "define_bounded_context",
    "get_board_state",
}

def get_participant_tools():
    """Return the subset of tool schemas available to participant agents."""
    return [t for t in TOOL_SCHEMAS if t["name"] in PARTICIPANT_TOOL_NAMES]


# ─────────────────────────────────────────────────────────────────────────────
# Participant Agent Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_participant_agent(
    agent_key: str,
    phase: int,
    board: BoardState,
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-5",
    verbose: bool = True,
) -> int:
    """
    Run a single participant agent through one workshop phase.

    The function executes the full Claude tool-use agentic loop:
      1. Build system prompt from agent config + phase instructions.
      2. Send initial message to Claude with the phase prompt.
      3. If Claude calls tools: execute them, return results, continue.
      4. When Claude stops calling tools: the agent's contribution is complete.

    Returns the number of tool calls made (for reporting).
    """
    agent = PARTICIPANT_AGENTS[agent_key]
    phase_prompt = PHASE_PROMPTS.get(phase, "")

    if not phase_prompt:
        return 0  # This agent has no specific role in this phase

    system_prompt = f"""You are the {agent["role"]} participating in an EventStorming workshop.

YOUR PROFESSIONAL IDENTITY:
{agent["backstory"]}

YOUR DOMAIN LENS:
{agent["lens"]}

WHAT YOU CONTRIBUTE:
{agent["contributes"]}

IMPORTANT BEHAVIORAL RULES:
- You contribute ONLY from your professional perspective. Stay in your lane.
- All domain events must be written in PAST TENSE ("Campaign Published", not "Publish Campaign").
- All commands must be written in IMPERATIVE ("Publish Campaign", not "Campaign was published").
- Never contribute elements that clearly belong to another agent's domain lens.
- When you disagree with something on the board, flag it as a Hot Spot — do NOT silently ignore it.
- Your language matters: use the words YOUR team actually uses in daily conversations.
- If a concept on the board uses the wrong vocabulary for your context, flag it.

CURRENT WORKSHOP CONTEXT:
Domain: {board.domain}
Scope: {board.scope}
Timeline: [{board.start_event}] → [{board.end_event}]
"""

    user_message = f"""You are now in Phase {phase} of the EventStorming workshop.

{phase_prompt}

Make your contributions now using the available tools.
"""

    messages = [{"role": "user", "content": user_message}]
    tools = get_participant_tools()
    tool_call_count = 0
    max_iterations = 15  # Safety guard against infinite loops

    if verbose:
        print(f"\n  ┌─ {agent_key} ({agent['role']}) — Phase {phase}")

    for iteration in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        # Collect any text the agent produced (for verbose logging)
        text_blocks = [b.text for b in response.content if b.type == "text"]
        if verbose and text_blocks:
            text_preview = " ".join(text_blocks)[:200].replace("\n", " ")
            print(f"  │  [{iteration+1}] {text_preview}{'...' if len(' '.join(text_blocks)) > 200 else ''}")

        # If Claude finished without calling a tool, the agent is done
        if response.stop_reason == "end_turn":
            break

        # Process tool calls
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break

        # Add Claude's response to the message history
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool and collect results
        tool_results = []
        for tool_block in tool_use_blocks:
            result = handle_tool_call(tool_block.name, tool_block.input, board)
            tool_call_count += 1
            if verbose:
                icon = "✓" if not result.startswith("⚠") and not result.startswith("🚫") else "⚠"
                print(f"  │  {icon} {tool_block.name}({_format_args(tool_block.input)}) → {result[:80]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            })

        # Return the tool results to Claude so it can continue reasoning
        messages.append({"role": "user", "content": tool_results})

    if verbose:
        print(f"  └─ {agent_key} complete: {tool_call_count} tool calls.")

    return tool_call_count


def _format_args(args: dict) -> str:
    """Compact one-line representation of tool arguments for logging."""
    parts = []
    for k, v in args.items():
        if isinstance(v, str):
            parts.append(f'{k}="{v[:30]}{"..." if len(v) > 30 else ""}"')
        elif isinstance(v, list):
            parts.append(f"{k}=[{len(v)} items]")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts[:3])  # Show first 3 args to keep logs readable
