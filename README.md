# EventStorming Facilitator Agent

A multi-agent EventStorming workshop facilitator powered by Claude, implementing the
methodology described in the article *"Event Storming Among Agents"* and the
`EventStormingFacilitator.md` Claude Skill.

---

## What This Does

This agent runs a complete eight-phase EventStorming workshop using six domain-expert
AI agents (CEO, CMO, Marketer, Research Analyst, Engineer, Product Manager) coordinated
by a Facilitator agent. At the end, it produces a structured set of Domain-Driven Design
artifacts: a Domain Event Catalog, Command Catalog, Aggregate Definitions, Policy
Register, Bounded Context Map, and a prose Domain Design Narrative.

---

## Project Structure

```
event_storming_agent/
├── board.py        — Shared board state (dataclasses for all DDD elements)
├── tools.py        — Tool schemas (JSON) and handlers that mutate board state
├── agents.py       — Participant agent configs, phase prompts, and runner
├── facilitator.py  — Facilitator orchestration, phase review, red team logic
├── synthesis.py    — DDD artifact generators (structured + LLM-powered narrative)
├── workshop.py     — Main orchestration loop tying all components together
├── main.py         — Entry point with CLI interface and default marketing example
└── README.md       — This file
```

---

## Prerequisites

Python 3.11 or later is required. Install the Anthropic SDK:

```bash
pip install anthropic
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=your-key-here
```

---

## Running the Workshop

To run the default example (a virtual marketing agency campaign lifecycle):

```bash
python main.py
```

To model a different domain:

```bash
python main.py \
  --domain "E-commerce Order Fulfillment" \
  --scope "From order placement to delivery confirmation and returns." \
  --start-event "Order Placed" \
  --end-event "Delivery Confirmed" \
  --output-dir my_workshop_output
```

To suppress verbose console output:

```bash
python main.py --quiet
```

---

## Architecture

The system is built around three concentric loops.

**The Workshop Loop** is the outermost loop. It iterates through all eight EventStorming
phases in sequence. The `workshop.py` module owns this loop.

**The Phase Loop** runs inside each phase. For each phase, the workshop runner invokes
the scheduled participant agents (different agents contribute in different phases), then
runs the Facilitator to review contributions and decide whether to advance. If the
Facilitator does not confirm acceptance criteria, the phase retries up to `max_retries`
times before proceeding anyway with a warning note.

**The Tool-Use Loop** is the innermost loop and is the standard Claude agentic pattern.
When Claude (as any agent) calls a tool, the application executes the handler, returns
the result to Claude, and Claude continues reasoning. This repeats until Claude emits
`stop_reason == "end_turn"`.

### Model Strategy

Participant agents (CEO, CMO, Marketer, Analyst, Engineer, PM) use `claude-sonnet-4-5`
by default. These agents make a high volume of calls during the workshop, and Sonnet
offers the best balance of reasoning quality and cost for this volume.

The Facilitator agent uses `claude-opus-4-5` by default. The Facilitator needs richer
reasoning for phase evaluation, acceptance criteria checking, red team challenge design,
and final synthesis. The additional capability is worth the higher cost for this role.

You can override both with CLI flags:

```bash
python main.py --facilitator-model claude-sonnet-4-5   # faster, lower cost
```

### Board State as Shared Memory

All agents share a single `BoardState` object. Every tool call mutates this object
synchronously — there is no message-passing between agents. The Facilitator injects
the current board state into each participant agent's context window before prompting
them to contribute. This is analogous to the paper roll on the wall in a real
EventStorming session: everyone can see everything that has been placed.

### Red Team Mechanism

A known failure mode in LLM multi-agent systems is premature consensus — agents agree
too quickly and produce a clean-looking model that misses the most important
disagreements. This agent addresses that risk with an explicit Red Team challenge.

After Phases 1, 5, and 6 (the phases most vulnerable to premature consensus), the
workshop runner checks whether fewer than two hot spots were raised during the phase.
If so, it invokes `run_red_team_challenge()`, which prompts the Engineer and Analyst
agents with a targeted skepticism challenge before the Facilitator runs its review.

### Output Files

All output files are saved to the `--output-dir` directory (default: `workshop_output`).
Each file is prefixed with a timestamp:

- `{timestamp}_board_phase{N}_attempt{A}.json` — Board state snapshot after each phase
- `{timestamp}_final_board.json` — Complete final board state
- `{timestamp}_ddd_artifacts.md` — The complete DDD artifact document

---

## Tool Reference

The ten tools available to agents are defined in `tools.py`. Participant agents have
access to nine of them; only the Facilitator can call `advance_workshop_phase`.

| Tool | Who Uses It | What It Does |
|------|-------------|--------------|
| `add_domain_event` | Participant agents | Places a past-tense domain event on the board |
| `add_command` | Participant agents | Places an imperative command that triggers an event |
| `add_read_model` | Participant agents | Places a green read model before a command |
| `add_external_system` | Participant agents | Places a pink external system node |
| `add_policy` | Participant agents | Places a lilac reactive business rule |
| `mark_hotspot` | All agents | Flags a red unresolved question, conflict, or risk |
| `define_aggregate` | Participant agents | Clusters events and commands into a named aggregate |
| `define_bounded_context` | Participant agents | Declares a named bounded context and its relationships |
| `get_board_state` | All agents | Returns a text snapshot of the current board |
| `advance_workshop_phase` | Facilitator only | Advances the workshop to the next phase |

---

## Extending the Agent

**Adding a new participant agent:** Add an entry to `PARTICIPANT_AGENTS` in `agents.py`
with the required `role`, `backstory`, `lens`, `contributes`, and `primary_phases` keys.
Then add the agent key to the appropriate phase schedules in `PHASE_AGENT_SCHEDULE` in
`workshop.py`.

**Changing the domain example:** Modify the `DEFAULT_*` constants in `main.py` or pass
CLI flags at runtime. No code changes are needed for a different domain.

**Running a single phase in isolation:** Import `run_participant_agent` from `agents.py`
and `run_facilitator_phase_review` from `facilitator.py` and call them directly with a
pre-configured `BoardState` object.

**Persisting the board between sessions:** Call `board.to_json()` to serialize and use
`json.loads()` plus manual reconstruction to reload. A future version could add a
`BoardState.from_json()` class method for this.

---

## References

This implementation is the companion code artifact for:

- Article: *"Event Storming Among Agents"* (Medium, April 2026)
- Skill file: `EventStormingFacilitator.md` (Claude Agent Skill)
- Methodology: Alberto Brandolini, *Introducing EventStorming* (Leanpub)
- Framework: Anthropic, *Building Effective Agents* (anthropic.com/research)
