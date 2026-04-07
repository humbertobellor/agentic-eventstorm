"""
tools.py — EventStorming Board Tools
======================================
These are the eight tools that participant agents and the Facilitator
can call to read from and write to the shared board state.

Each tool is defined in two parts:
  1. A JSON-schema dict consumed by the Anthropic API as a tool definition.
  2. A Python handler function that receives the validated arguments and
     mutates (or reads) the BoardState object.

The Facilitator has access to all eight tools.
Participant agents are given a restricted subset depending on their phase.
"""

from board import (
    BoardState, DomainEvent, Command, Aggregate,
    Policy, ReadModel, ExternalSystem, HotSpot, BoundedContext,
)


# ─────────────────────────────────────────────────────────────────────────────
# Tool JSON Schemas  (passed to anthropic client as `tools=TOOL_SCHEMAS`)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "add_domain_event",
        "description": (
            "Place a domain event on the EventStorming board. "
            "Write the name in past tense: 'Campaign Published', 'Order Shipped'. "
            "Domain events are the orange stickies — something meaningful that happened."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Past-tense noun-phrase. Example: 'Campaign Published'"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the business significance of this event."
                },
                "originating_agent": {
                    "type": "string",
                    "description": "Your role title, e.g. 'CMO', 'Engineer'."
                },
                "phase_added": {
                    "type": "integer",
                    "description": "Current workshop phase (default 1).",
                    "default": 1
                },
            },
            "required": ["name", "originating_agent"],
        },
    },
    {
        "name": "add_command",
        "description": (
            "Place a command that causes a domain event. "
            "Write in imperative: 'Publish Campaign', 'Ship Order'. "
            "Commands are blue stickies placed immediately left of their event."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Imperative verb-phrase. Example: 'Publish Campaign'"
                },
                "triggers_event": {
                    "type": "string",
                    "description": "Exact name of the domain event this command produces."
                },
                "actor": {
                    "type": "string",
                    "description": "Role that issues this command, e.g. 'Marketing Specialist', 'System'."
                },
                "data_needed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Data fields required to execute this command.",
                },
            },
            "required": ["name", "triggers_event", "actor"],
        },
    },
    {
        "name": "add_read_model",
        "description": (
            "Place a read model — the information an actor needs to see before "
            "issuing a command. Read models are green stickies: dashboards, "
            "reports, or any view the user consults first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Descriptive noun phrase. Example: 'Campaign Performance Dashboard'"
                },
                "description": {"type": "string"},
                "required_before_command": {
                    "type": "string",
                    "description": "The command this read model precedes."
                },
            },
            "required": ["name", "required_before_command"],
        },
    },
    {
        "name": "add_external_system",
        "description": (
            "Place an external system — a third-party or black-box service that "
            "emits or receives events. External systems are pink stickies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "e.g. 'Ad Platform', 'CRM System'"},
                "description": {"type": "string"},
                "emits_events": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Domain events this system produces."
                },
                "receives_events": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Domain events this system consumes."
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "add_policy",
        "description": (
            "Define a reactive business rule: 'Whenever [Event], then [Command]'. "
            "Policies are lilac stickies that connect an event to a subsequent command. "
            "Flag if this policy crosses a bounded context boundary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "triggered_by_event": {
                    "type": "string",
                    "description": "The domain event that triggers this policy."
                },
                "triggers_command": {
                    "type": "string",
                    "description": "The command this policy issues in response."
                },
                "rule_description": {
                    "type": "string",
                    "description": "Natural-language description of the business rule."
                },
                "crosses_context_boundary": {
                    "type": "boolean",
                    "description": "True if the event and command belong to different bounded contexts.",
                    "default": False
                },
            },
            "required": ["triggered_by_event", "triggers_command", "rule_description"],
        },
    },
    {
        "name": "mark_hotspot",
        "description": (
            "Flag an unresolved question, conflict, or area of risk on the board. "
            "Hot Spots are red stickies. Mark High severity for anything that would "
            "block the workshop from producing a valid model."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Clear description of the unresolved issue."
                },
                "related_events": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Domain events this hot spot is associated with."
                },
                "type": {
                    "type": "string",
                    "enum": ["question", "conflict", "risk", "complexity"],
                },
                "severity": {
                    "type": "string",
                    "enum": ["High", "Medium", "Low"],
                },
                "flagged_by": {
                    "type": "string",
                    "description": "Agent role that flagged this hot spot."
                },
            },
            "required": ["description", "type", "severity"],
        },
    },
    {
        "name": "define_aggregate",
        "description": (
            "Define an aggregate — a named cluster of domain objects with a shared "
            "lifecycle and consistency rules. Aggregates receive commands and produce "
            "events. Name them with a single business noun: 'Campaign', 'Order'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "related_events": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Domain events that belong to this aggregate's lifecycle."
                },
                "related_commands": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Commands this aggregate handles."
                },
                "invariants": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Business rules this aggregate must always enforce."
                },
                "bounded_context": {
                    "type": "string",
                    "description": "Which bounded context this aggregate belongs to."
                },
            },
            "required": ["name", "related_events", "related_commands"],
        },
    },
    {
        "name": "define_bounded_context",
        "description": (
            "Declare a named bounded context and its relationships to other contexts. "
            "A bounded context is a boundary of consistent language and shared meaning. "
            "Name it after the vocabulary used inside it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "aggregates": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Aggregates that live inside this context."
                },
                "upstream_contexts": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Contexts that provide data or events to this context."
                },
                "downstream_contexts": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Contexts that consume data or events from this context."
                },
                "relationship_type": {
                    "type": "string",
                    "enum": [
                        "Shared Kernel", "Customer-Supplier",
                        "Anti-Corruption Layer", "Published Language", "Conformist"
                    ],
                    "description": "The DDD relationship pattern between this and adjacent contexts."
                },
                "integration_events": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Events that cross this context's boundary."
                },
            },
            "required": ["name", "aggregates"],
        },
    },
    {
        "name": "get_board_state",
        "description": (
            "Retrieve the current state of the EventStorming board. "
            "Use this to review what has been placed so far before contributing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filter_by": {
                    "type": "string",
                    "enum": [
                        "all", "domain_events", "commands", "aggregates",
                        "policies", "hotspots", "bounded_contexts",
                        "read_models", "external_systems"
                    ],
                    "default": "all"
                },
                "bounded_context": {
                    "type": "string",
                    "description": "Optional: filter by a specific bounded context name."
                },
            },
        },
    },
    {
        "name": "advance_workshop_phase",
        "description": (
            "Move the workshop to the next phase after confirming all acceptance "
            "criteria for the current phase are met. Only the Facilitator should call this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "current_phase": {
                    "type": "integer",
                    "description": "The phase number being completed (0–7)."
                },
                "acceptance_criteria_confirmed": {
                    "type": "boolean",
                    "description": "True only when all criteria for this phase are satisfied."
                },
                "facilitator_notes": {
                    "type": "string",
                    "description": "Summary notes from the Facilitator before advancing."
                },
            },
            "required": ["current_phase", "acceptance_criteria_confirmed"],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Tool Handlers  (called by the agent loop after Claude emits a tool_use block)
# ─────────────────────────────────────────────────────────────────────────────

def handle_tool_call(tool_name: str, tool_input: dict, board: BoardState) -> str:
    """
    Dispatch a tool call to the appropriate handler and return a
    human-readable result string that Claude will see as the tool result.
    """
    handlers = {
        "add_domain_event":      _add_domain_event,
        "add_command":           _add_command,
        "add_read_model":        _add_read_model,
        "add_external_system":   _add_external_system,
        "add_policy":            _add_policy,
        "mark_hotspot":          _mark_hotspot,
        "define_aggregate":      _define_aggregate,
        "define_bounded_context": _define_bounded_context,
        "get_board_state":       _get_board_state,
        "advance_workshop_phase": _advance_workshop_phase,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return f"ERROR: Unknown tool '{tool_name}'."
    return handler(tool_input, board)


def _add_domain_event(args: dict, board: BoardState) -> str:
    name = args["name"].strip()
    # Deduplicate — case-insensitive check
    existing = [e.name for e in board.domain_events]
    if any(e.lower() == name.lower() for e in existing):
        return (f"⚠ Domain event '{name}' already exists on the board. "
                f"This duplication signals a potential Ubiquitous Language conflict "
                f"— log a Hot Spot if the two events have different meanings.")
    event = DomainEvent(
        name=name,
        description=args.get("description", ""),
        originating_agent=args.get("originating_agent", ""),
        phase_added=args.get("phase_added", board.current_phase),
    )
    board.domain_events.append(event)
    return (f"✓ Domain Event added: '{name}' "
            f"(contributed by {event.originating_agent}). "
            f"Board now has {len(board.domain_events)} domain events.")


def _add_command(args: dict, board: BoardState) -> str:
    cmd = Command(
        name=args["name"].strip(),
        triggers_event=args["triggers_event"],
        actor=args["actor"],
        data_needed=args.get("data_needed", []),
    )
    board.commands.append(cmd)
    return (f"✓ Command added: '{cmd.name}' → triggers '{cmd.triggers_event}' "
            f"| Actor: {cmd.actor}.")


def _add_read_model(args: dict, board: BoardState) -> str:
    rm = ReadModel(
        name=args["name"].strip(),
        description=args.get("description", ""),
        required_before_command=args["required_before_command"],
    )
    board.read_models.append(rm)
    return f"✓ Read Model added: '{rm.name}' | Required before: {rm.required_before_command}."


def _add_external_system(args: dict, board: BoardState) -> str:
    ext = ExternalSystem(
        name=args["name"].strip(),
        description=args.get("description", ""),
        emits_events=args.get("emits_events", []),
        receives_events=args.get("receives_events", []),
    )
    board.external_systems.append(ext)
    return f"✓ External System added: '{ext.name}'."


def _add_policy(args: dict, board: BoardState) -> str:
    policy = Policy(
        triggered_by_event=args["triggered_by_event"],
        triggers_command=args["triggers_command"],
        rule_description=args["rule_description"],
        crosses_context_boundary=args.get("crosses_context_boundary", False),
    )
    board.policies.append(policy)
    cross = " ⚡ (crosses context boundary — integration point)" if policy.crosses_context_boundary else ""
    return (f"✓ Policy added: Whenever [{policy.triggered_by_event}] "
            f"→ [{policy.triggers_command}]{cross}.")


def _mark_hotspot(args: dict, board: BoardState) -> str:
    hs = HotSpot(
        description=args["description"],
        related_events=args.get("related_events", []),
        type=args.get("type", "question"),
        severity=args.get("severity", "Medium"),
        flagged_by=args.get("flagged_by", ""),
    )
    board.hotspots.append(hs)
    return (f"⚠ Hot Spot flagged [{hs.severity}] {hs.type.upper()}: {hs.description}. "
            f"Board now has {board.count_unresolved_hotspots()} open hot spots.")


def _define_aggregate(args: dict, board: BoardState) -> str:
    agg = Aggregate(
        name=args["name"].strip(),
        related_events=args.get("related_events", []),
        related_commands=args.get("related_commands", []),
        invariants=args.get("invariants", []),
        bounded_context=args.get("bounded_context", ""),
    )
    board.aggregates.append(agg)
    # Also tag each domain event with this aggregate
    for event in board.domain_events:
        if event.name in agg.related_events:
            event.aggregate = agg.name
    return (f"✓ Aggregate defined: '{agg.name}' "
            f"| Events: {', '.join(agg.related_events[:3])}{'...' if len(agg.related_events) > 3 else ''} "
            f"| Invariants: {len(agg.invariants)}.")


def _define_bounded_context(args: dict, board: BoardState) -> str:
    bc = BoundedContext(
        name=args["name"].strip(),
        aggregates=args.get("aggregates", []),
        upstream_contexts=args.get("upstream_contexts", []),
        downstream_contexts=args.get("downstream_contexts", []),
        relationship_type=args.get("relationship_type", ""),
        integration_events=args.get("integration_events", []),
    )
    board.bounded_contexts.append(bc)
    # Tag aggregates and their events with this context
    for agg in board.aggregates:
        if agg.name in bc.aggregates:
            agg.bounded_context = bc.name
            for event in board.domain_events:
                if event.name in agg.related_events:
                    event.bounded_context = bc.name
    return (f"✓ Bounded Context defined: '{bc.name}' "
            f"| Aggregates: {', '.join(bc.aggregates)} "
            f"| Relationship: {bc.relationship_type or 'unspecified'}.")


def _get_board_state(args: dict, board: BoardState) -> str:
    return board.to_context_summary(
        filter_by=args.get("filter_by", "all"),
        bounded_context=args.get("bounded_context"),
    )


def _advance_workshop_phase(args: dict, board: BoardState) -> str:
    current = args["current_phase"]
    confirmed = args["acceptance_criteria_confirmed"]
    notes = args.get("facilitator_notes", "")

    if not confirmed:
        return (f"⚠ Phase {current} cannot be advanced — acceptance criteria not confirmed. "
                f"Review open hot spots and incomplete elements before advancing.")
    if board.has_high_severity_open_hotspots() and current >= 7:
        open_hs = [h.description for h in board.hotspots if h.severity == "High" and not h.resolved]
        return (f"🚫 Cannot advance past Phase 7 with High-severity open Hot Spots: "
                f"{'; '.join(open_hs)}")

    board.current_phase = current + 1
    if notes:
        board.facilitator_notes.append(f"[Phase {current} → {current+1}] {notes}")
    return (f"✓ Workshop advanced from Phase {current} to Phase {current + 1}. "
            f"Board: {len(board.domain_events)} events, "
            f"{len(board.commands)} commands, "
            f"{len(board.aggregates)} aggregates, "
            f"{len(board.bounded_contexts)} contexts, "
            f"{board.count_unresolved_hotspots()} open hot spots.")
