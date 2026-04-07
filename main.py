"""
main.py — Entry Point and Example Usage
=========================================
Run this file to execute a complete EventStorming workshop for a
virtual digital marketing agency campaign lifecycle domain.

Usage:
    python main.py

Environment variables required:
    ANTHROPIC_API_KEY — your Anthropic API key

Optional CLI arguments:
    --domain        Custom domain name
    --scope         Custom scope description
    --start-event   Custom start event name
    --end-event     Custom end event name
    --quiet         Suppress verbose output
    --output-dir    Directory for saving artifacts (default: workshop_output)
"""

import argparse
import os
import sys

# Validate API key before importing workshop (fails fast with a clear message)
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("\nError: ANTHROPIC_API_KEY environment variable is not set.")
    print("Set it with:  export ANTHROPIC_API_KEY=your-key-here")
    sys.exit(1)

from workshop import run_workshop


# ─────────────────────────────────────────────────────────────────────────────
# Default Example: Virtual Marketing Agency
# ─────────────────────────────────────────────────────────────────────────────
# This is the domain used throughout the article "Event Storming Among Agents".
# Change these defaults or use CLI flags to model a different domain.

DEFAULT_DOMAIN      = "Digital Marketing Agency — Campaign Lifecycle"
DEFAULT_SCOPE       = (
    "From the moment a client submits a campaign brief to the moment campaign "
    "performance is reported back to the client. Includes strategy, creative "
    "execution, technical deployment, measurement, and reporting."
)
DEFAULT_START_EVENT = "Client Brief Received"
DEFAULT_END_EVENT   = "Campaign Performance Reported"


def main():
    parser = argparse.ArgumentParser(
        description="EventStorming Facilitator Agent — powered by Claude"
    )
    parser.add_argument("--domain",      default=DEFAULT_DOMAIN,
                        help="The business domain to model.")
    parser.add_argument("--scope",       default=DEFAULT_SCOPE,
                        help="A one-sentence scope description.")
    parser.add_argument("--start-event", default=DEFAULT_START_EVENT,
                        help="The leftmost event on the timeline.")
    parser.add_argument("--end-event",   default=DEFAULT_END_EVENT,
                        help="The rightmost event on the timeline.")
    parser.add_argument("--quiet",       action="store_true",
                        help="Suppress verbose console output.")
    parser.add_argument("--output-dir",  default="workshop_output",
                        help="Directory for saving artifact files.")
    parser.add_argument("--participant-model", default="claude-sonnet-4-5",
                        help="Claude model for domain expert agents.")
    parser.add_argument("--facilitator-model", default="claude-opus-4-5",
                        help="Claude model for the Facilitator agent.")

    args = parser.parse_args()

    artifacts, board = run_workshop(
        domain=args.domain,
        scope=args.scope,
        start_event=args.start_event,
        end_event=args.end_event,
        participant_model=args.participant_model,
        facilitator_model=args.facilitator_model,
        verbose=not args.quiet,
        output_dir=args.output_dir,
    )

    # Print a concise final summary to stdout regardless of verbosity
    print("\n" + "═" * 70)
    print("WORKSHOP COMPLETE — Summary")
    print("═" * 70)
    print(f"Domain events discovered:  {len(board.domain_events)}")
    print(f"Commands identified:       {len(board.commands)}")
    print(f"Aggregates defined:        {len(board.aggregates)}")
    print(f"Bounded contexts:          {len(board.bounded_contexts)}")
    print(f"Policies:                  {len(board.policies)}")
    print(f"Open hot spots remaining:  {board.count_unresolved_hotspots()}")
    print(f"\nArtifacts written to: {args.output_dir}/")
    print("═" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
