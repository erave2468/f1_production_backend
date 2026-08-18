from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

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

def sync_season(
    year: int,
    force: bool = False,
) -> None:
    configure_fastf1_cache()

    now = datetime.now(UTC).replace(tzinfo=None)

    with SessionLocal() as db:

        # 수동 강제 동기화
        if force:
            log.info(
                "Force sync requested for %s",
                year,
            )

            ingest_reference_data(db, year)
            ingest_schedule(db, year)

            collect_due_sessions(
                db,
                year,
                now,
            )

            return

        grand_prix_windows = get_grand_prix_windows(
            db,
            year,
        )

        for (
            grand_prix_id,
            round_number,
            display_name,
            first_start,
            last_start,
        ) in grand_prix_windows:

            state = get_sync_state(
                db,
                grand_prix_id,
            )

            pre_start = first_start - timedelta(
                hours=settings.sync_pre_event_hours
            )

            live_end = last_start + timedelta(
                minutes=settings.collect_after_start_minutes
            )

            post_start = last_start + timedelta(
                hours=settings.sync_post_event_hours
            )

            post_end = post_start + timedelta(
                hours=24
            )

            # ─────────────────────────
            # 경기 전날
            # ─────────────────────────

            if (
                pre_start <= now < first_start
                and state["pre_event_synced_at"] is None
            ):
                log.info(
                    "Pre-event sync: %s R%s",
                    display_name,
                    round_number,
                )

                ingest_reference_data(db, year)
                ingest_schedule(db, year)

                mark_sync_state(
                    db,
                    grand_prix_id,
                    "pre_event_synced_at",
                    now,
                )

                return

            # ─────────────────────────
            # 경기 주말
            # ─────────────────────────

            if first_start <= now <= live_end:

                last_live = state[
                    "last_live_synced_at"
                ]

                live_due = (
                    last_live is None
                    or now - last_live
                    >= timedelta(
                        minutes=settings.sync_live_interval_minutes
                    )
                )

                if live_due:
                    log.info(
                        "Live weekend sync: %s R%s",
                        display_name,
                        round_number,
                    )

                    ingest_reference_data(
                        db,
                        year,
                    )

                    ingest_schedule(
                        db,
                        year,
                    )

                    collect_due_sessions(
                        db,
                        year,
                        now,
                    )

                    mark_sync_state(
                        db,
                        grand_prix_id,
                        "last_live_synced_at",
                        now,
                    )

                    return

            # ─────────────────────────
            # 경기 다음날
            # ─────────────────────────

            if (
                post_start <= now < post_end
                and state["post_event_synced_at"] is None
            ):
                log.info(
                    "Post-event sync: %s R%s",
                    display_name,
                    round_number,
                )

                ingest_reference_data(
                    db,
                    year,
                )

                ingest_schedule(
                    db,
                    year,
                )

                collect_due_sessions(
                    db,
                    year,
                    now,
                )

                mark_sync_state(
                    db,
                    grand_prix_id,
                    "post_event_synced_at",
                    now,
                )

                return

        log.info(
            "No scheduled sync due for %s",
            year,
        )

def sync_configured_seasons() -> None:
    for year in settings.collection_season_list:
        sync_season(year)
def collect_due_sessions(db, year: int, now: datetime) -> None:
    cutoff = now - timedelta(
        minutes=settings.collect_after_start_minutes
    )

    oldest = now - timedelta(
        days=settings.collector_lookback_days
    )

    due = db.execute(
        select(
            SessionModel,
            GrandPrix.round_number,
        )
        .join(
            GrandPrix,
            GrandPrix.id == SessionModel.grand_prix_id,
        )
        .where(
            GrandPrix.season_year == year,
            SessionModel.scheduled_start.is_not(None),
            SessionModel.scheduled_start >= oldest,
            SessionModel.scheduled_start <= cutoff,
            func.lower(
                func.coalesce(
                    SessionModel.status,
                    "scheduled",
                )
            ) != "completed",
        )
        .order_by(
            SessionModel.scheduled_start.desc()
        )
        .limit(
            settings.collector_max_sessions_per_run
        )
    ).all()

    completed_race_rounds: set[int] = set()

    for session_row, round_number in due:
        try:
            log.info(
                "Collecting %s R%s %s",
                year,
                round_number,
                session_row.type.value,
            )

            ingest_session(
                db,
                year,
                round_number,
                session_row.type.value,
            )

            if session_row.type == SessionType.R:
                completed_race_rounds.add(
                    int(round_number)
                )

        except Exception:
            db.rollback()

            log.exception(
                "Collection failed for %s R%s %s; "
                "will retry next run",
                year,
                round_number,
                session_row.type.value,
            )

    for round_number in completed_race_rounds:
        try:
            ingest_standings(
                db,
                year,
                round_number,
            )

        except Exception:
            db.rollback()

            log.exception(
                "Standings sync failed for %s R%s",
                year,
                round_number,
            )

def get_sync_state(db, grand_prix_id: int):
    db.execute(
        text(
            """
            INSERT IGNORE INTO grand_prix_sync_state (
                grand_prix_id
            )
            VALUES (:grand_prix_id)
            """
        ),
        {"grand_prix_id": grand_prix_id},
    )
    db.commit()

    return db.execute(
        text(
            """
            SELECT
                pre_event_synced_at,
                last_live_synced_at,
                post_event_synced_at
            FROM grand_prix_sync_state
            WHERE grand_prix_id = :grand_prix_id
            """
        ),
        {"grand_prix_id": grand_prix_id},
    ).mappings().one()

def mark_sync_state(
    db,
    grand_prix_id: int,
    field: str,
    synced_at: datetime,
) -> None:
    allowed_fields = {
        "pre_event_synced_at",
        "last_live_synced_at",
        "post_event_synced_at",
    }

    if field not in allowed_fields:
        raise ValueError(f"Invalid sync state field: {field}")

    db.execute(
        text(
            f"""
            UPDATE grand_prix_sync_state
            SET {field} = :synced_at
            WHERE grand_prix_id = :grand_prix_id
            """
        ),
        {
            "grand_prix_id": grand_prix_id,
            "synced_at": synced_at,
        },
    )
    db.commit()

def get_grand_prix_windows(db, year: int):
    return db.execute(
        select(
            GrandPrix.id,
            GrandPrix.round_number,
            GrandPrix.display_name,
            func.min(
                SessionModel.scheduled_start
            ).label("first_start"),
            func.max(
                SessionModel.scheduled_start
            ).label("last_start"),
        )
        .join(
            SessionModel,
            SessionModel.grand_prix_id == GrandPrix.id,
        )
        .where(
            GrandPrix.season_year == year,
            SessionModel.scheduled_start.is_not(None),
        )
        .group_by(
            GrandPrix.id,
            GrandPrix.round_number,
            GrandPrix.display_name,
        )
        .order_by(
            GrandPrix.round_number
        )
    ).all()

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize FastF1 data into RDS"
    )

    parser.add_argument(
        "--season",
        type=int,
        action="append",
        help=(
            "Season to sync; repeatable. "
            "Defaults to COLLECT_SEASONS."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Run a safe sync immediately, "
            "ignoring the GP schedule window."
        ),
    )

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s: "
            "%(message)s"
        ),
    )

    args = build_parser().parse_args()

    years = (
        args.season
        or settings.collection_season_list
    )

    for year in years:
        sync_season(
            year,
            force=args.force,
        )


if __name__ == "__main__":
    main()
