from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal

from app.models import (
    CircuitLayout,
    CircuitRecord,
    Constructor,
    Driver,
    GrandPrix,
)


RECORD_TYPE_ALIASES = {
    "LAP": "RACE_LAP",
    "RACE_LAP": "RACE_LAP",

    "TRACK": "TRACK_LAP",
    "TRACK_LAP": "TRACK_LAP",
}


def clean_optional(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


def parse_lap_time_us(
    value: str,
) -> int:
    """
    지원:
        1:30.983
        58.790
        1:02:03.456

    반환:
        microseconds
    """

    value = value.strip()

    if not value:
        raise ValueError(
            "lap_time is empty"
        )

    parts = value.split(":")

    try:
        if len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = float(parts[0])

        elif len(parts) == 2:
            hours = 0
            minutes = int(parts[0])
            seconds = float(parts[1])

        elif len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])

        else:
            raise ValueError

    except ValueError as exc:
        raise ValueError(
            f"Invalid lap_time: {value!r}"
        ) from exc

    total_seconds = (
        hours * 3600
        + minutes * 60
        + seconds
    )

    if total_seconds <= 0:
        raise ValueError(
            f"Invalid lap_time: {value!r}"
        )

    return round(
        total_seconds * 1_000_000
    )


def normalize_record_type(
    value: str,
) -> str:
    value = value.strip().upper()

    record_type = (
        RECORD_TYPE_ALIASES.get(value)
    )

    if record_type is None:
        raise ValueError(
            "Unsupported record_type "
            f"{value!r}. "
            "Use RACE_LAP or TRACK_LAP."
        )

    return record_type


def seed_records(
    csv_path: Path,
    *,
    apply: bool,
) -> None:

    csv_path = csv_path.resolve()

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV not found: {csv_path}"
        )

    created = 0
    updated = 0

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        required = {
            "layout_ref",
            "record_type",
            "driver_ref",
            "constructor_ref",
            "year",
            "lap_time",
        }

        if not reader.fieldnames:
            raise ValueError(
                "CSV has no header"
            )

        missing = (
            required
            - set(reader.fieldnames)
        )

        if missing:
            raise ValueError(
                "Missing CSV columns: "
                + ", ".join(
                    sorted(missing)
                )
            )

        with SessionLocal() as db:
            try:
                for line_no, row in enumerate(
                    reader,
                    start=2,
                ):
                    layout_ref = (
                        row["layout_ref"]
                        .strip()
                    )

                    record_type = (
                        normalize_record_type(
                            row["record_type"]
                        )
                    )

                    driver_ref = (
                        row["driver_ref"]
                        .strip()
                    )

                    constructor_ref = (
                        row["constructor_ref"]
                        .strip()
                    )

                    year_raw = (
                        row["year"].strip()
                    )

                    if not year_raw:
                        raise ValueError(
                            f"Line {line_no}: "
                            "year is empty"
                        )

                    record_year = int(
                        year_raw
                    )

                    lap_time_us = (
                        parse_lap_time_us(
                            row["lap_time"]
                        )
                    )

                    source = clean_optional(
                        row.get("source")
                    )

                    source_url = (
                        clean_optional(
                            row.get(
                                "source_url"
                            )
                        )
                    )

                    # ─────────────────
                    # Layout
                    # ─────────────────

                    layout = db.scalar(
                        select(CircuitLayout)
                        .where(
                            CircuitLayout.layout_ref
                            == layout_ref
                        )
                    )

                    if layout is None:
                        raise ValueError(
                            f"Line {line_no}: "
                            "unknown layout_ref "
                            f"{layout_ref!r}"
                        )

                    # ─────────────────
                    # Driver
                    # ─────────────────

                    driver = db.scalar(
                        select(Driver)
                        .where(
                            Driver.driver_ref
                            == driver_ref
                        )
                    )

                    if driver is None:
                        raise ValueError(
                            f"Line {line_no}: "
                            "unknown driver_ref "
                            f"{driver_ref!r}"
                        )

                    # ─────────────────
                    # Constructor
                    # ─────────────────

                    constructor = db.scalar(
                        select(Constructor)
                        .where(
                            Constructor.constructor_ref
                            == constructor_ref
                        )
                    )

                    if constructor is None:
                        raise ValueError(
                            f"Line {line_no}: "
                            "unknown constructor_ref "
                            f"{constructor_ref!r}"
                        )

                    # 해당 연도 GP가 DB에 있으면
                    # grand_prix_id도 자동 연결.
                    #
                    # 역사 데이터가 DB에 없으면
                    # NULL이어도 문제 없음.
                    gp = db.scalar(
                        select(GrandPrix)
                        .where(
                            GrandPrix.circuit_id
                            == layout.circuit_id,

                            GrandPrix.season_year
                            == record_year,
                        )
                        .limit(1)
                    )

                    # ─────────────────
                    # UPSERT
                    # ─────────────────

                    record = db.scalar(
                        select(CircuitRecord)
                        .where(
                            CircuitRecord
                            .circuit_layout_id
                            == layout.id,

                            CircuitRecord
                            .record_type
                            == record_type,
                        )
                    )

                    if record is None:
                        record = CircuitRecord(
                            circuit_layout_id=(
                                layout.id
                            ),

                            record_type=(
                                record_type
                            ),

                            driver_id=(
                                driver.id
                            ),

                            constructor_id=(
                                constructor.id
                            ),

                            grand_prix_id=(
                                gp.id
                                if gp
                                else None
                            ),

                            record_year=(
                                record_year
                            ),

                            lap_time_us=(
                                lap_time_us
                            ),

                            source=source,
                            source_url=(
                                source_url
                            ),
                        )

                        db.add(record)

                        action = "CREATE"
                        created += 1

                    else:
                        record.driver_id = (
                            driver.id
                        )

                        record.constructor_id = (
                            constructor.id
                        )

                        record.grand_prix_id = (
                            gp.id
                            if gp
                            else None
                        )

                        record.record_year = (
                            record_year
                        )

                        record.lap_time_us = (
                            lap_time_us
                        )

                        record.source = source
                        record.source_url = (
                            source_url
                        )

                        action = "UPDATE"
                        updated += 1

                    db.flush()

                    print(
                        f"{action:<6} "
                        f"{layout_ref:<25} "
                        f"{record_type:<10} "
                        f"{driver_ref:<15} "
                        f"{row['lap_time']}"
                    )

                print()
                print(
                    f"created : {created}"
                )
                print(
                    f"updated : {updated}"
                )

                if apply:
                    db.commit()

                    print()
                    print(
                        "Changes committed."
                    )

                else:
                    db.rollback()

                    print()
                    print(
                        "DRY RUN: "
                        "no changes committed."
                    )

            except Exception:
                db.rollback()
                raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Seed circuit records "
            "from CSV"
        )
    )

    parser.add_argument(
        "csv",
        type=Path,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Commit changes. "
            "Without this option "
            "the command is dry-run."
        ),
    )

    args = parser.parse_args()

    seed_records(
        args.csv,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()