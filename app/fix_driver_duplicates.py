from __future__ import annotations

import argparse

from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import (
    CircuitRecord,
    Driver,
    DriverOfTheDay,
    DriverStanding,
    GrandPrix,
    SeasonDriverEntry,
    SessionEntry,
)


# duplicate_id -> canonical_id
MERGES = {
    48: 1,    # ALB
    49: 2,    # ALO
    34: 3,    # ANT
    40: 5,    # BEA
    45: 7,    # BOR
    51: 8,    # BOT
    46: 10,   # COL
    39: 13,   # GAS
    41: 14,   # HAD
    36: 15,   # HAM
    42: 18,   # HUL
    44: 20,   # LAW
    38: 21,   # LEC
    35: 23,   # NOR
    43: 24,   # OCO
    37: 25,   # PIA
    52: 26,   # PER
    33: 27,   # RUS
    47: 28,   # SAI
    50: 29,   # STR
    55: 54,   # TSU
}


def min_value(a, b):
    values = [x for x in (a, b) if x is not None]
    return min(values) if values else None


def max_value(a, b):
    values = [x for x in (a, b) if x is not None]
    return max(values) if values else None


def merge_driver(
    db,
    duplicate_id: int,
    canonical_id: int,
) -> None:
    duplicate = db.get(Driver, duplicate_id)
    canonical = db.get(Driver, canonical_id)

    if duplicate is None:
        print(f"SKIP duplicate {duplicate_id}: not found")
        return

    if canonical is None:
        raise RuntimeError(
            f"Canonical driver {canonical_id} not found"
        )

    print(
        f"{duplicate.id} {duplicate.full_name}"
        f" -> "
        f"{canonical.id} {canonical.full_name}"
    )

    # ─────────────────────────────
    # season_driver_entries
    # ─────────────────────────────

    duplicate_entries = db.scalars(
        select(SeasonDriverEntry)
        .where(
            SeasonDriverEntry.driver_id
            == duplicate_id
        )
    ).all()

    for entry in duplicate_entries:
        target = db.scalar(
            select(SeasonDriverEntry)
            .where(
                SeasonDriverEntry.season_year
                == entry.season_year,
                SeasonDriverEntry.driver_id
                == canonical_id,
                SeasonDriverEntry.constructor_id
                == entry.constructor_id,
            )
        )

        if target is None:
            entry.driver_id = canonical_id
            continue

        # 이미지가 duplicate 쪽에만 있으면 보존
        if (
            target.portrait_image_id is None
            and entry.portrait_image_id is not None
        ):
            target.portrait_image_id = (
                entry.portrait_image_id
            )

        if target.color is None:
            target.color = entry.color

        if target.car_number is None:
            target.car_number = entry.car_number

        target.start_round = min_value(
            target.start_round,
            entry.start_round,
        )

        target.end_round = max_value(
            target.end_round,
            entry.end_round,
        )

        if entry.is_primary_driver:
            target.is_primary_driver = True

        db.delete(entry)

    db.flush()

    # ─────────────────────────────
    # driver_standings
    # ─────────────────────────────

    duplicate_standings = db.scalars(
        select(DriverStanding)
        .where(
            DriverStanding.driver_id
            == duplicate_id
        )
    ).all()

    for standing in duplicate_standings:
        target = db.scalar(
            select(DriverStanding)
            .where(
                DriverStanding.season_year
                == standing.season_year,
                DriverStanding.after_round
                == standing.after_round,
                DriverStanding.driver_id
                == canonical_id,
            )
        )

        if target is None:
            standing.driver_id = canonical_id
        else:
            # canonical standing을 우선 보존
            if target.constructor_id is None:
                target.constructor_id = (
                    standing.constructor_id
                )

            if target.podiums is None:
                target.podiums = standing.podiums

            db.delete(standing)

    db.flush()

    # ─────────────────────────────
    # session_entries
    # ─────────────────────────────

    duplicate_session_entries = db.scalars(
        select(SessionEntry)
        .where(
            SessionEntry.driver_id
            == duplicate_id
        )
    ).all()

    for entry in duplicate_session_entries:
        conflict = db.scalar(
            select(SessionEntry.id)
            .where(
                SessionEntry.session_id
                == entry.session_id,
                SessionEntry.driver_id
                == canonical_id,
            )
        )

        if conflict is not None:
            raise RuntimeError(
                "SessionEntry conflict: "
                f"session={entry.session_id}, "
                f"duplicate={duplicate_id}, "
                f"canonical={canonical_id}"
            )

        # entry.id는 그대로 유지되므로
        # laps/results/stints도 전부 보존됨
        entry.driver_id = canonical_id

    db.flush()

    # ─────────────────────────────
    # 단순 FK
    # ─────────────────────────────

    db.execute(
        update(GrandPrix)
        .where(
            GrandPrix.winning_driver_id
            == duplicate_id
        )
        .values(
            winning_driver_id=canonical_id
        )
    )

    db.execute(
        update(DriverOfTheDay)
        .where(
            DriverOfTheDay.driver_id
            == duplicate_id
        )
        .values(
            driver_id=canonical_id
        )
    )

    db.execute(
        update(CircuitRecord)
        .where(
            CircuitRecord.driver_id
            == duplicate_id
        )
        .values(
            driver_id=canonical_id
        )
    )

    db.flush()

    # 최종 duplicate driver 삭제
    db.delete(duplicate)

    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes",
    )

    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            for duplicate_id, canonical_id in MERGES.items():
                merge_driver(
                    db,
                    duplicate_id,
                    canonical_id,
                )

            if args.apply:
                db.commit()
                print()
                print("Driver merge committed.")
            else:
                db.rollback()
                print()
                print(
                    "DRY RUN complete. "
                    "No changes committed."
                )

        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()