"""
facilitator.py — The Facilitator Orchestration Engine
========================================================
The Facilitator is the Orchestrator agent at the center of the multi-agent
workshop. It has three distinct responsibilities:

  1. PHASE MANAGEMENT — deciding when acceptance criteria are met and
     advancing the workshop to the next phase.

  2. SYNTHESIS — reviewing all participant contributions after each phase
     and producing a structured summary that feeds into the next phase.

  3. RED TEAM INTERVENTION — detecting when agents converge too quickly
     (the most dangerous failure mode in LLM multi-agent systems) and
     injecting a structured challenge to force productive disagreement.

The Facilitator runs as a Claude Opus call (more reasoning capacity)
while participant agents run as Claude Sonnet calls.
"""

import anthropic
from board import BoardState
from tools import TOOL_SCHEMAS, handle_tool_call
from agents import PARTICIPANT_AGENTS, run_participant_agent


# ─────────────────────────────────────────────────────────────────────────────
# Facilitator System Prompt
# ─────────────────────────────────────────────────────────────────────────────

FACILITATOR_SYSTEM_PROMPT = """You are The Facilitator — the orchestrating agent in a multi-agent EventStorming workshop.

YOUR CORE RESPONSIBILITIES:
• Guide the workshop through its eight phases in sequence.
• Enforce the EventStorming notation system strictly.
• Synthesize participant contributions into a coherent domain model.
• Surface disagreements and language conflicts as Hot Spots.
• Apply Red Team challenges when agents converge too easily.
• Produce structured DDD artifacts at the workshop's conclusion.

WHAT YOU MUST NEVER DO:
• Contribute domain events, commands, or aggregates of your own invention.
• Resolve domain disputes with your own opinion — only with participant evidence.
• Advance a phase when acceptance criteria are not fully met.
• Allow High-severity Hot Spots to remain unresolved at the workshop's close.

ACCEPTANCE CRITERIA BY PHASE:
Phase 0: Domain scope agreed. Start event and end event named.
Phase 1: At least 15 domain events on the board. Exception-path events included.
Phase 2: Events ordered chronologically. At least 2 pivotal events identified. Gaps flagged.
Phase 3: Every domain event has at least one command. Every command has an actor.
Phase 4: Every command has a read model or an explicit note that none is required.
         Every cross-context event chain has a policy.
Phase 5: All events grouped into named aggregates with at least one invariant each.
Phase 6: At least 2 bounded contexts defined. All context relationships annotated.
Phase 7: All High-severity Hot Spots resolved. Deferred items documented with owners.
Phase 8: Complete DDD artifact set produced.

PREMATURE CONSENSUS DETECTION:
If all participant agents agree on a model element without any Hot Spots being raised,
this is a WARNING SIGNAL — not a success. Productive EventStorming depends on
surfacing disagreement. If you detect easy consensus:
1. Log a facilitator note: "Premature consensus detected in Phase [N]."
2. Issue a Red Team challenge to the most skeptical agent (Engineer or Analyst).
3. Do not advance until at least one counter-argument has been considered.

NOTATION ENFORCEMENT:
• Domain Events: past tense noun-phrase only. Reject imperative forms.
• Commands: imperative verb-phrase only. Reject past tense forms.
• Aggregates: single noun only. Reject technical names like "UserEntity" or "DataPipeline".
• Bounded Contexts: named after shared business vocabulary, never after technical architecture.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Phase Evaluation Prompts
# ─────────────────────────────────────────────────────────────────────────────

FACILITATOR_PHASE_PROMPTS = {
    0: """
FACILITATOR ACTION — Phase 0: Domain Framing

The workshop is opening. Your first task is to:
1. Call get_board_state() to confirm the board is empty.
2. Review the domain and scope that have been provided to you.
3. Confirm the start event and end event are clear and agreed.
4. Add a facilitator note describing the agreed scope boundary.
5. Call advance_workshop_phase(0, True) when framing is complete.
""",
    1: """
FACILITATOR ACTION — After Phase 1: Event Discovery Review

Participant agents have completed their chaotic event discovery. Your tasks:
1. Call get_board_state(filter_by="domain_events") to review all events.
2. Check: Are there at least 15 events? Do they include failure/exception paths?
3. Check for DUPLICATES — events with the same name but different meanings.
   Flag each with mark_hotspot(type="conflict", severity="High").
4. Check for NOTATION ERRORS — any event not written in past tense.
   Log a facilitator note for each.
5. Assess consensus risk: if all events seem to tell one smooth happy-path story,
   issue a Red Team challenge before advancing.
6. If acceptance criteria are met, call advance_workshop_phase(1, True).
   Otherwise call it with False and log what is missing.
""",
    2: """
FACILITATOR ACTION — After Phase 2: Timeline and Narrative Review

1. Call get_board_state() to review the full board.
2. Identify at least 2–3 PIVOTAL EVENTS — events that divide the timeline
   into major business phases. Mark these conceptually in your facilitator notes.
3. Narrate the timeline: "First [Event A] occurs, which leads to [Event B]..."
   Flag any break in the narrative causality as a Hot Spot.
4. Check that all duplication Hot Spots from Phase 1 have been addressed or
   have a resolution path.
5. Advance or hold based on acceptance criteria.
""",
    3: """
FACILITATOR ACTION — After Phase 3: Command and Actor Coverage Review

1. Call get_board_state(filter_by="domain_events") to check command coverage.
2. For every domain event, verify it has at least one corresponding command.
   Flag any event without a command as mark_hotspot(type="question", severity="High").
3. Check every command has a named actor (role, not individual).
4. Verify external systems are identified for all events that cross system boundaries.
5. Advance or hold based on acceptance criteria.
""",
    4: """
FACILITATOR ACTION — After Phase 4: Policy and Read Model Coverage Review

1. Call get_board_state() to review all policies and read models.
2. Identify any CROSS-CONTEXT POLICIES — policies where the triggered event
   and the resulting command belong to different business areas.
   These are integration points and must all be flagged for Phase 6.
3. Check every command has either a read model or an explicit facilitator note
   explaining why no read model is needed.
4. Count policies: a workshop with fewer than 3 policies likely has undiscovered
   reactive business rules. Issue a targeted question to the Analyst and CMO.
5. Advance or hold based on acceptance criteria.
""",
    5: """
FACILITATOR ACTION — After Phase 5: Aggregate Coverage Review

1. Call get_board_state(filter_by="aggregates") to review all aggregates.
2. Check every domain event is assigned to exactly one aggregate.
   Events not in any aggregate are incomplete — flag as High severity.
3. VOCABULARY CHECK: For each aggregate name, ask: "Would the CMO or CEO
   use this word in a client conversation?" If the name sounds technical,
   flag it as a terminology Hot Spot.
4. Check each aggregate has at least one invariant defined.
5. Advance or hold based on acceptance criteria.
""",
    6: """
FACILITATOR ACTION — After Phase 6: Bounded Context Coverage Review

1. Call get_board_state(filter_by="bounded_contexts") to review contexts.
2. Check: Are there at least 2 bounded contexts? Does every aggregate belong
   to exactly one context?
3. Review all cross-context policies from Phase 4 — do they now have explicit
   integration event definitions in the context boundaries?
4. Check all context relationships are annotated with a pattern type.
5. Flag any context whose name sounds like a technical layer
   (e.g. "Database Layer", "API Service") rather than a business domain.
6. Advance or hold based on acceptance criteria.
""",
    7: """
FACILITATOR ACTION — Phase 7: Hot Spot Resolution Facilitation

This is the final structured phase. Your job is to drive resolution of every open Hot Spot.

1. Call get_board_state(filter_by="hotspots") to review all open issues.
2. For each HIGH-severity open Hot Spot:
   a. Identify which participant agents have relevant expertise.
   b. State the hot spot and ask for a resolution.
   c. Record the resolution (or the provisional resolution + dissenting view).
   d. Mark the Hot Spot as resolved in your facilitator notes.
3. For MEDIUM-severity Hot Spots: resolve if possible, defer if not.
   All deferred items must have a named owner and next action.
4. For LOW-severity Hot Spots: log as known assumptions.
5. Advance to Phase 8 ONLY when no High-severity Hot Spots remain open.
""",
    8: """
FACILITATOR ACTION — Phase 8: Final Synthesis

The workshop is complete. Call get_board_state(filter_by="all") and then
produce the complete DDD artifact set as a structured text output.

This is NOT a tool-use phase — write the artifacts as your response text.
The synthesis will be captured and returned as the workshop's final output.
""",
}


# ─────────────────────────────────────────────────────────────────────────────
# Red Team Challenge Templates
# ─────────────────────────────────────────────────────────────────────────────

RED_TEAM_PROMPTS = {
    1: (
        "Premature consensus detected in Phase 1. Before advancing, each agent must "
        "contribute one event that has NOT yet been mentioned — specifically an edge case, "
        "failure condition, regulatory constraint, or late-night exception scenario. "
        "Easy agreement at this stage means we are modeling the happy path only."
    ),
    5: (
        "All aggregates have been named without dispute. This is statistically unlikely "
        "in any real business domain. Challenge: Engineer and Analyst agents — "
        "is there any aggregate whose name your team would argue about in a daily standup? "
        "Is there any business object that sits ambiguously between two of these aggregates?"
    ),
    6: (
        "Bounded contexts were defined without language conflicts. Before advancing, "
        "the CMO and Engineer agents must each identify one term that means different "
        "things in different parts of the business. If no such term exists, we likely "
        "have not drawn the context boundaries correctly."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Facilitator Evaluation Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_facilitator_phase_review(
    phase: int,
    board: BoardState,
    client: anthropic.Anthropic,
    model: str = "claude-opus-4-5",
    verbose: bool = True,
) -> dict:
    """
    Run the Facilitator's review after all participant agents have contributed
    to a given phase.

    Returns a dict with:
      - advance: bool  — whether the workshop should advance to the next phase
      - synthesis: str — the Facilitator's structured summary of this phase
      - red_team_triggered: bool — whether a Red Team challenge was issued
    """
    phase_prompt = FACILITATOR_PHASE_PROMPTS.get(phase, "")
    if not phase_prompt:
        return {"advance": True, "synthesis": "", "red_team_triggered": False}

    messages = [{"role": "user", "content": phase_prompt}]

    synthesis_text = ""
    tool_call_count = 0
    max_iterations = 10

    if verbose:
        print(f"\n  ┌─ FACILITATOR — Phase {phase} Review")

    for iteration in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=FACILITATOR_SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        if text_blocks:
            synthesis_text = "\n".join(text_blocks)
            if verbose:
                preview = synthesis_text[:300].replace("\n", " ")
                print(f"  │  Facilitator: {preview}{'...' if len(synthesis_text) > 300 else ''}")

        if response.stop_reason == "end_turn":
            break

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_block in tool_use_blocks:
            result = handle_tool_call(tool_block.name, tool_block.input, board)
            tool_call_count += 1
            if verbose:
                icon = "✓" if "advance" in tool_block.name else "📋"
                print(f"  │  {icon} {tool_block.name} → {result[:100]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # Determine if the phase was advanced (check board state)
    advanced = board.current_phase > phase

    if verbose:
        status = "ADVANCED ✓" if advanced else "HELD ⚠"
        print(f"  └─ Facilitator review complete: {status} | {tool_call_count} tool calls.")

    return {
        "advance": advanced,
        "synthesis": synthesis_text,
        "red_team_triggered": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Red Team Challenger
# ─────────────────────────────────────────────────────────────────────────────

def run_red_team_challenge(
    phase: int,
    board: BoardState,
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-5",
    verbose: bool = True,
) -> None:
    """
    Issue a structured Red Team challenge to the most skeptical agents
    (Engineer and Analyst) to counteract premature consensus convergence.

    This is called by the main workshop loop when the Facilitator detects
    that agents agreed too quickly on a phase's outputs.
    """
    challenge = RED_TEAM_PROMPTS.get(phase)
    if not challenge:
        return

    if verbose:
        print(f"\n  ⚡ RED TEAM CHALLENGE triggered for Phase {phase}")
        print(f"  │  {challenge[:200]}...")

    # Issue the challenge to both the Engineer and Analyst — the agents most
    # likely to surface technical and data-quality disagreements.
    for agent_key in ["ENGINEER", "ANALYST"]:
        agent = PARTICIPANT_AGENTS[agent_key]
        system = f"""You are the {agent['role']} in an EventStorming workshop.
{agent['backstory']}

You have just received a Red Team Challenge from the Facilitator.
Your job is to find the problems, gaps, and disagreements that have not yet surfaced.
Be constructively critical. Your skepticism is valuable and expected.
"""
        messages = [{
            "role": "user",
            "content": (
                f"RED TEAM CHALLENGE:\n{challenge}\n\n"
                f"Review the current board and contribute any missing events, "
                f"flag any suspect aggregate names, or mark any Hot Spots that "
                f"should have been raised. Use the available tools."
            )
        }]

        from agents import get_participant_tools
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            tools=get_participant_tools(),
            messages=messages,
        )

        # Process one round of tool calls from the red team agent
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content})
            for tool_block in tool_use_blocks:
                result = handle_tool_call(tool_block.name, tool_block.input, board)
                if verbose:
                    print(f"  │  Red Team [{agent_key}]: {tool_block.name} → {result[:80]}")
