"""Command-line generator for inspectable Required Queue checkpoints."""

import argparse

from Tools.tests.fixtures.e2e.required_queue_scenarios import (
    generate_required_queue_checkpoint,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a current Required Queue Integration checkpoint")
    parser.add_argument(
        "--scenario", required=True,
        choices=("maintenance-closed", "closed-both", "terminal-closed"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    generate_required_queue_checkpoint(
        args.scenario, args.output, args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
