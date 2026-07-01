"""CLI entry point for the CoffeeBench OCL integration probe."""

from __future__ import annotations

import argparse
import json

from .shim import build_phase0_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe CoffeeBench OCL integration readiness.")
    parser.add_argument(
        "--module-prefix",
        default="coffeebench",
        help="Python module prefix for CoffeeBench if imported under a nonstandard name.",
    )
    args = parser.parse_args()
    print(json.dumps(build_phase0_report(args.module_prefix), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
