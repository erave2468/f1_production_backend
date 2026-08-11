from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.ingest.fastf1_collector import (
    configure_fastf1_cache,
    ingest_reference_data,
    ingest_schedule,
    ingest_session,
    ingest_standings,
)
from app.models import GrandPrix, SessionModel, SessionType

log = logging.getLogger(__name__)


def sync_season(year: int) -> None:
    '''Synchronize metadata and sessions that should already be finished.

    It deliberately waits COLLECT_AFTER_START_MINUTES after scheduled start so the
    collector does not mark a live session as completed. The systemd timer reruns this
    function later if a session was not ready or failed temporarily.
    '''
    '''
    세션 동기화
    경기시간 기다리고 업뎃함
    세션 동기화 안되면 systemd 타이머가 다시킴
    '''
    configure_fastf1_cache()
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(minutes=settings.collect_after_start_minutes)
    oldest = now - timedelta(days=settings.collector_lookback_days)

    with SessionLocal() as db:
        log.info("Syncing %s reference data", year)
        ingest_reference_data(db, year)
        log.info("Syncing %s event schedule", year)
        ingest_schedule(db, year)

        due = db.execute(
            select(SessionModel, GrandPrix.round_number)
            .join(GrandPrix, GrandPrix.id == SessionModel.grand_prix_id)
            .where(
                GrandPrix.season_year == year,
                SessionModel.scheduled_start.is_not(None),
                SessionModel.scheduled_start >= oldest,
                SessionModel.scheduled_start <= cutoff,
                func.lower(
                    func.coalesce(SessionModel.status, "scheduled")
                ) != "completed",
            )
            .order_by(SessionModel.scheduled_start.desc())
            .limit(settings.collector_max_sessions_per_run)
        ).all()

        completed_race_rounds: set[int] = set()
        for session_row, round_number in due:
            try:
                log.info("Collecting %s R%s %s", year, round_number, session_row.type.value)
                ingest_session(db, year, round_number, session_row.type.value)
                if session_row.type == SessionType.R:
                    completed_race_rounds.add(round_number)
            except Exception:
                db.rollback()
                log.exception("Collection failed for %s R%s %s; will retry next run", year, round_number, session_row.type.value)
        
        
        for round_number in completed_race_rounds:
            try:
                ingest_standings(db, year, int(round_number))
            except Exception:
                db.rollback()
                log.exception(
                    "Standings sync failed for %s R%s",
                    year,
                    round_number,
                )


def sync_configured_seasons() -> None:
    for year in settings.collection_season_list:
        sync_season(year)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize FastF1 data into RDS")
    parser.add_argument("--season", type=int, action="append", help="Season to sync; repeatable. Defaults to COLLECT_SEASONS.")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args()
    years = args.season or settings.collection_season_list
    for year in years:
        sync_season(year)


if __name__ == "__main__":
    main()
