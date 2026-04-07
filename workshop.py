"""
workshop.py — Main Workshop Orchestration Loop
================================================
This module ties all components together into a single run_workshop() function.
It executes the eight EventStorming phases in sequence, coordinating participant
agents and the Facilitator, applying red team challenges when appropriate,
and producing the final DDD artifact set at the end.

Typical execution flow:
  Phase 0: Facilitator frames the domain.
  Phases 1–7: Participant agents contribute → Facilitator reviews → advance or retry.
  Phase 8: Synthesis — generate the complete DDD artifact document.
"""

import os
import json
from datetime import datetime
import anthropic

from board import BoardState
from agents import PARTICIPANT_AGENTS, run_participant_agent
from facilitator import (
    run_facilitator_phase_review,
    run_red_team_challenge,
    RED_TEAM_PROMPTS,
)
from synthesis import generate_all_artifacts


# ─────────────────────────────────────────────────────────────────────────────
# Which agents contribute in which phases
# ─────────────────────────────────────────────────────────────────────────────

# Mapping from phase number to the list of participant agent keys that contribute.
# The Facilitator always runs after the participant agents in each phase.
PHASE_AGENT_SCHEDULE = {
    0: [],                                              # Facilitator only
    1: ["CEO", "CMO", "MARKETER", "ANALYST", "ENGINEER", "PM"],  # All agents
    2: ["CEO", "CMO", "ENGINEER", "ANALYST"],           # Timeline ordering
    3: ["CMO", "MARKETER", "ENGINEER", "PM"],           # Commands and actors
    4: ["CMO", "MARKETER", "ANALYST", "PM"],            # Policies and read models
    5: ["ENGINEER", "PM", "CMO", "CEO"],                # Aggregates (CEO/CMO for vocab)
    6: ["CEO", "CMO", "ENGINEER", "ANALYST"],           # Bounded contexts
    7: ["CEO", "CMO", "MARKETER", "ANALYST", "ENGINEER", "PM"],  # Hot spot resolution
}

# Phases that benefit from a Red Team challenge if consensus was smooth
RED_TEAM_ELIGIBLE_PHASES = {1, 5, 6}


def run_workshop(
    domain: str,
    scope: str,
    start_event: str,
    end_event: str,
    participant_model: str = "claude-sonnet-4-5",
    facilitator_model: str = "claude-opus-4-5",
    max_retries_per_phase: int = 2,
    verbose: bool = True,
    save_board_snapshots: bool = True,
    output_dir: str = "workshop_output",
) -> tuple[str, BoardState]:
    """
    Run a complete EventStorming workshop and return the DDD artifact document
    and the final board state.

    Parameters
    ----------
    domain : str
        A concise name for the business domain being modeled.
        Example: "Digital Marketing Agency — Campaign Lifecycle"

    scope : str
        A one-sentence description of what is in scope for this workshop.
        Example: "From client brief submission to campaign performance reporting."

    start_event : str
        The leftmost event on the timeline (the domain trigger).
        Example: "Client Brief Received"

    end_event : str
        The rightmost event on the timeline (the desired outcome).
        Example: "Campaign Performance Reported"

    participant_model : str
        The Claude model to use for domain expert agents (default: claude-sonnet-4-5).
        Sonnet is fast and cost-effective for the high volume of participant calls.

    facilitator_model : str
        The Claude model to use for the Facilitator agent (default: claude-opus-4-5).
        Opus is used here for the richer reasoning needed for synthesis and evaluation.

    max_retries_per_phase : int
        How many times the Facilitator may retry a phase if acceptance criteria
        are not met on the first pass. Default 2.

    verbose : bool
        Print progress to stdout throughout the workshop. Default True.

    save_board_snapshots : bool
        Save a JSON snapshot of the board state after each phase. Default True.

    output_dir : str
        Directory for saving output files. Default "workshop_output".

    Returns
    -------
    (artifacts: str, board: BoardState)
        artifacts — the complete Markdown DDD artifact document
        board — the final board state object (for further programmatic use)
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Initialize the board ──────────────────────────────────────────────────
    board = BoardState(
        domain=domain,
        scope=scope,
        start_event=start_event,
        end_event=end_event,
        current_phase=0,
    )

    _print_header(domain, scope, start_event, end_event, verbose)

    # ── Phase loop ────────────────────────────────────────────────────────────
    for phase in range(8):

        _print_phase_header(phase, verbose)

        for attempt in range(max_retries_per_phase + 1):

            # 1. Run participant agents for this phase
            agents_this_phase = PHASE_AGENT_SCHEDULE.get(phase, [])
            total_tool_calls = 0

            for agent_key in agents_this_phase:
                calls = run_participant_agent(
                    agent_key=agent_key,
                    phase=phase,
                    board=board,
                    client=client,
                    model=participant_model,
                    verbose=verbose,
                )
                total_tool_calls += calls

            if verbose and agents_this_phase:
                print(f"\n  → {len(agents_this_phase)} agents contributed "
                      f"{total_tool_calls} total tool calls in Phase {phase}.")

            # 2. Apply a Red Team challenge if this phase is eligible and it
            #    was the first attempt (not a retry — we only challenge once)
            if attempt == 0 and phase in RED_TEAM_ELIGIBLE_PHASES:
                # Heuristic: if fewer than 2 hotspots were raised this phase,
                # consensus may be premature — trigger the Red Team.
                hotspots_this_phase = sum(
                    1 for h in board.hotspots
                    if not h.resolved
                )
                if hotspots_this_phase < 2:
                    run_red_team_challenge(
                        phase=phase,
                        board=board,
                        client=client,
                        model=participant_model,
                        verbose=verbose,
                    )

            # 3. Run the Facilitator review for this phase
            result = run_facilitator_phase_review(
                phase=phase,
                board=board,
                client=client,
                model=facilitator_model,
                verbose=verbose,
            )

            # 4. Save board snapshot after Facilitator review
            if save_board_snapshots:
                snap_path = os.path.join(
                    output_dir,
                    f"{timestamp}_board_phase{phase}_attempt{attempt}.json"
                )
                with open(snap_path, "w") as f:
                    f.write(board.to_json())

            # 5. Check if the Facilitator advanced the phase
            if result["advance"]:
                if verbose:
                    print(f"\n  ✓ Phase {phase} complete. Advancing.\n")
                break
            elif attempt < max_retries_per_phase:
                if verbose:
                    print(f"\n  ⚠ Phase {phase} acceptance criteria not met. "
                          f"Retry {attempt + 1}/{max_retries_per_phase}...\n")
            else:
                if verbose:
                    print(f"\n  ⚠ Phase {phase} max retries reached. "
                          f"Proceeding with incomplete phase.\n")
                board.current_phase = phase + 1
                board.facilitator_notes.append(
                    f"Phase {phase} was advanced despite incomplete acceptance criteria "
                    f"after {max_retries_per_phase} retries."
                )

    # ── Phase 8: Synthesis ────────────────────────────────────────────────────
    _print_phase_header(8, verbose)
    if verbose:
        print("  Generating DDD artifact set...")

    artifacts = generate_all_artifacts(board, client, include_narrative=True)

    # Save the final artifact document
    artifact_path = os.path.join(output_dir, f"{timestamp}_ddd_artifacts.md")
    with open(artifact_path, "w") as f:
        f.write(artifacts)

    # Save the final board state
    board_path = os.path.join(output_dir, f"{timestamp}_final_board.json")
    with open(board_path, "w") as f:
        f.write(board.to_json())

    if verbose:
        print(f"\n{'═' * 70}")
        print(f"  WORKSHOP COMPLETE")
        print(f"  Domain events:    {len(board.domain_events)}")
        print(f"  Commands:         {len(board.commands)}")
        print(f"  Aggregates:       {len(board.aggregates)}")
        print(f"  Bounded contexts: {len(board.bounded_contexts)}")
        print(f"  Policies:         {len(board.policies)}")
        print(f"  Hot spots:        {len(board.hotspots)} "
              f"({board.count_unresolved_hotspots()} open)")
        print(f"  Artifacts saved:  {artifact_path}")
        print(f"  Board saved:      {board_path}")
        print(f"{'═' * 70}")

    return artifacts, board


# ─────────────────────────────────────────────────────────────────────────────
# Console Formatting Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_header(domain, scope, start_event, end_event, verbose):
    if not verbose:
        return
    print(f"\n{'═' * 70}")
    print(f"  EventStorming Workshop — {domain}")
    print(f"{'═' * 70}")
    print(f"  Scope:       {scope}")
    print(f"  Start event: {start_event}")
    print(f"  End event:   {end_event}")
    print(f"{'─' * 70}\n")


PHASE_NAMES = {
    0: "Setup and Domain Framing",
    1: "Chaotic Domain Event Discovery",
    2: "Timeline Ordering and Narrative Walk",
    3: "Commands, Actors, and External Systems",
    4: "Policies and Read Models",
    5: "Aggregate Identification",
    6: "Bounded Context Definition",
    7: "Hot Spot Resolution",
    8: "Synthesis and DDD Artifact Generation",
}


def _print_phase_header(phase, verbose):
    if not verbose:
        return
    name = PHASE_NAMES.get(phase, f"Phase {phase}")
    print(f"\n{'─' * 70}")
    print(f"  PHASE {phase}: {name}")
    print(f"{'─' * 70}")
