"""
board.py — EventStorming Board State
=====================================
The board is the shared memory of the entire workshop. Every tool call
mutates this state object, and every participant agent receives a
serialized snapshot of it before contributing. Think of it as the
paper roll on the wall that everyone in the room can see at all times.
"""

from dataclasses import dataclass, field
from typing import Optional
import json


# ─────────────────────────────────────────────
# Core Domain Elements
# ─────────────────────────────────────────────

@dataclass
class DomainEvent:
    """An orange sticky note. Something meaningful that happened, in past tense."""
    name: str
    description: str = ""
    originating_agent: str = ""
    phase_added: int = 1
    aggregate: str = ""               # filled in during Phase 5
    bounded_context: str = ""         # filled in during Phase 6
    is_pivotal: bool = False          # marked by facilitator in Phase 2


@dataclass
class Command:
    """A blue sticky note. The imperative action that caused a domain event."""
    name: str
    triggers_event: str
    actor: str
    data_needed: list[str] = field(default_factory=list)
    read_model_required: str = ""     # filled in during Phase 4


@dataclass
class Aggregate:
    """A large yellow sticky note. A cluster of domain objects with a shared lifecycle."""
    name: str
    related_events: list[str] = field(default_factory=list)
    related_commands: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    bounded_context: str = ""


@dataclass
class Policy:
    """A lilac sticky note. A reactive business rule: 'Whenever X, then Y'."""
    triggered_by_event: str
    triggers_command: str
    rule_description: str
    crosses_context_boundary: bool = False
    source_context: str = ""
    target_context: str = ""


@dataclass
class ReadModel:
    """A green sticky note. Information an actor needs before issuing a command."""
    name: str
    description: str = ""
    required_before_command: str = ""
    bounded_context: str = ""


@dataclass
class ExternalSystem:
    """A pink sticky note. A third-party or black-box service."""
    name: str
    description: str = ""
    emits_events: list[str] = field(default_factory=list)
    receives_events: list[str] = field(default_factory=list)


@dataclass
class HotSpot:
    """A red sticky note. An unresolved question, conflict, or area of risk."""
    description: str
    related_events: list[str] = field(default_factory=list)
    # type: question | conflict | risk | complexity
    type: str = "question"
    # severity: High | Medium | Low
    severity: str = "Medium"
    flagged_by: str = ""
    resolved: bool = False
    resolution: str = ""
    dissenting_view: str = ""         # always record minority positions


@dataclass
class BoundedContext:
    """An emergent language boundary discovered during the workshop."""
    name: str
    aggregates: list[str] = field(default_factory=list)
    upstream_contexts: list[str] = field(default_factory=list)
    downstream_contexts: list[str] = field(default_factory=list)
    # relationship_type: Shared Kernel | Customer-Supplier |
    #                    Anti-Corruption Layer | Published Language | Conformist
    relationship_type: str = ""
    integration_events: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# The Board — Workshop Shared State
# ─────────────────────────────────────────────

@dataclass
class BoardState:
    """
    The complete shared state of the EventStorming workshop.
    Every participant agent reads from this before contributing,
    and every tool call writes to it.
    """
    # Workshop metadata
    domain: str = ""
    scope: str = ""
    start_event: str = ""
    end_event: str = ""
    current_phase: int = 0

    # Board elements — populated progressively through the workshop
    domain_events: list[DomainEvent] = field(default_factory=list)
    commands: list[Command] = field(default_factory=list)
    aggregates: list[Aggregate] = field(default_factory=list)
    policies: list[Policy] = field(default_factory=list)
    read_models: list[ReadModel] = field(default_factory=list)
    external_systems: list[ExternalSystem] = field(default_factory=list)
    hotspots: list[HotSpot] = field(default_factory=list)
    bounded_contexts: list[BoundedContext] = field(default_factory=list)

    # Facilitator bookkeeping
    pivotal_events: list[str] = field(default_factory=list)
    facilitator_notes: list[str] = field(default_factory=list)
    phase_outputs: dict = field(default_factory=dict)

    def to_context_summary(self, filter_by: str = "all",
                           bounded_context: Optional[str] = None) -> str:
        """
        Serialize the board into a human-readable summary suitable for
        injecting into a participant agent's context window.
        Optionally filter by element type or bounded context name.
        """
        lines = [
            f"=== CURRENT BOARD STATE (Phase {self.current_phase}) ===",
            f"Domain: {self.domain}",
            f"Scope:  {self.scope}",
            f"Timeline: [{self.start_event}] → [{self.end_event}]",
            "",
        ]

        def maybe(condition, header, items, formatter):
            """Only render a section if it has items and passes the filter."""
            if (filter_by in ("all", condition)) and items:
                filtered = items
                if bounded_context:
                    filtered = [i for i in items
                                if getattr(i, "bounded_context", "") in ("", bounded_context)]
                if filtered:
                    lines.append(f"── {header} ({len(filtered)}) ──")
                    for item in filtered:
                        lines.append(f"  • {formatter(item)}")
                    lines.append("")

        maybe("domain_events", "DOMAIN EVENTS", self.domain_events,
              lambda e: f"[{'★ PIVOTAL ' if e.is_pivotal else ''}{e.name}]"
                        f"  ← {e.originating_agent}"
                        f"{f'  | Aggregate: {e.aggregate}' if e.aggregate else ''}"
                        f"{f'  | Context: {e.bounded_context}' if e.bounded_context else ''}")

        maybe("commands", "COMMANDS", self.commands,
              lambda c: f"[{c.name}]  → triggers: {c.triggers_event}  | Actor: {c.actor}")

        maybe("aggregates", "AGGREGATES", self.aggregates,
              lambda a: f"[{a.name}]"
                        f"  Events: {', '.join(a.related_events[:3])}{'...' if len(a.related_events) > 3 else ''}"
                        f"  | Context: {a.bounded_context}")

        maybe("policies", "POLICIES", self.policies,
              lambda p: f"Whenever [{p.triggered_by_event}] → [{p.triggers_command}]"
                        f"{'  ⚡ crosses context boundary' if p.crosses_context_boundary else ''}")

        maybe("read_models", "READ MODELS", self.read_models,
              lambda r: f"[{r.name}]  needed before: {r.required_before_command}")

        maybe("external_systems", "EXTERNAL SYSTEMS", self.external_systems,
              lambda x: f"[{x.name}]")

        maybe("hotspots", "HOT SPOTS", self.hotspots,
              lambda h: f"[{h.severity}] {h.type.upper()}: {h.description}"
                        f"{'  ✓ Resolved' if h.resolved else '  ⚠ OPEN'}")

        maybe("bounded_contexts", "BOUNDED CONTEXTS", self.bounded_contexts,
              lambda b: f"[{b.name}]"
                        f"  Aggregates: {', '.join(b.aggregates)}"
                        f"  | {b.relationship_type}")

        if self.pivotal_events:
            lines.append(f"── PIVOTAL EVENTS ({len(self.pivotal_events)}) ──")
            for e in self.pivotal_events:
                lines.append(f"  ★ {e}")
            lines.append("")

        if filter_by == "all" and self.facilitator_notes:
            lines.append("── FACILITATOR NOTES ──")
            for note in self.facilitator_notes[-5:]:   # last 5 only to save context
                lines.append(f"  📋 {note}")

        return "\n".join(lines)

    def event_names(self) -> list[str]:
        return [e.name for e in self.domain_events]

    def has_high_severity_open_hotspots(self) -> bool:
        return any(h.severity == "High" and not h.resolved for h in self.hotspots)

    def count_unresolved_hotspots(self) -> int:
        return sum(1 for h in self.hotspots if not h.resolved)

    def to_json(self) -> str:
        """Full JSON serialization for persistence or debugging."""
        def serialize(obj):
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            if isinstance(obj, list):
                return [serialize(i) for i in obj]
            return obj

        return json.dumps(self.__dict__, default=serialize, indent=2)
