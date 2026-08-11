from __future__ import annotations

import argparse
import logging

from app.db import SessionLocal
from app.ingest.fastf1_collector import (
    configure_fastf1_cache,
    ingest_reference_data,
    ingest_round,
    ingest_schedule,
    ingest_session,
    ingest_standings,
)
from app.sync import sync_season


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FastF1 -> RDS/MySQL collector")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("reference", help="drivers/constructors/circuits")
    p.add_argument("year", type=int)

    p = sub.add_parser("schedule", help="grand prix + sessions")
    p.add_argument("year", type=int)

    p = sub.add_parser("session", help="one session")
    p.add_argument("year", type=int)
    p.add_argument("round", type=int)
    p.add_argument("session", help="FP1/FP2/FP3/Q/SQ/S/R")

    p = sub.add_parser("standings", help="standings after a round")
    p.add_argument("year", type=int)
    p.add_argument("round", type=int)

    p = sub.add_parser("round", help="all scheduled sessions + standings")
    p.add_argument("year", type=int)
    p.add_argument("round", type=int)

    p = sub.add_parser("sync", help="metadata + all due unfinished sessions")
    p.add_argument("year", type=int)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args()
    if args.command == "sync":
        sync_season(args.year)
        return

    configure_fastf1_cache()
    with SessionLocal() as db:
        if args.command == "reference":
            ingest_reference_data(db, args.year)
        elif args.command == "schedule":
            ingest_schedule(db, args.year)
        elif args.command == "session":
            ingest_session(db, args.year, args.round, args.session)
        elif args.command == "standings":
            ingest_standings(db, args.year, args.round)
        elif args.command == "round":
            ingest_round(db, args.year, args.round)


if __name__ == "__main__":
    main()
