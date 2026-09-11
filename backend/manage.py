#!/usr/bin/env python
"""Small operational CLI: create tables, bootstrap defaults, seed demo data."""
from __future__ import annotations

import argparse
import sys

from app.db import Base, SessionLocal, engine
from app.services.bootstrap import bootstrap


def cmd_create_all(_: argparse.Namespace) -> None:
    import app.models  # noqa: F401  (registers metadata)

    Base.metadata.create_all(engine)
    print("Tables created.")


def cmd_bootstrap(_: argparse.Namespace) -> None:
    with SessionLocal() as db:
        bootstrap(db)
    print("Cycle, days, periods and constraint weights are in place.")


def cmd_seed(args: argparse.Namespace) -> None:
    import app.models  # noqa: F401

    from app.seed import seed_demo

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        result = seed_demo(db, seed=args.seed)
    if result.get("skipped"):
        print("Database is not empty, demo seed skipped.")
    else:
        print("Demo dataset created:", result)


def cmd_seed_school(args: argparse.Namespace) -> None:
    import app.models  # noqa: F401

    from app.seed_school import SchoolSpec, seed_school

    Base.metadata.create_all(engine)
    spec = SchoolSpec(seed=args.seed, solo_share=args.solo_share)
    with SessionLocal() as db:
        result = seed_school(db, spec)
    if result.get("skipped"):
        print("Database is not empty, school seed skipped.")
    else:
        print("School dataset created:")
        for key, value in result.items():
            print(f"  {key:14s} {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="School Timetable Optimizer management CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create-all").set_defaults(func=cmd_create_all)
    sub.add_parser("bootstrap").set_defaults(func=cmd_bootstrap)
    seed_parser = sub.add_parser("seed-demo")
    seed_parser.add_argument("--seed", type=int, default=42)
    seed_parser.set_defaults(func=cmd_seed)
    school_parser = sub.add_parser(
        "seed-school", help="Full-size dataset: 8 gymnasium classes + 4 lyceum classes"
    )
    school_parser.add_argument("--seed", type=int, default=7)
    school_parser.add_argument("--solo-share", type=float, default=0.27, dest="solo_share")
    school_parser.set_defaults(func=cmd_seed_school)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
