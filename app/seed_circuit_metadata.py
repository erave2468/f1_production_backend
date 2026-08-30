from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Circuit, CircuitLayout


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def clean_optional_int(
    value: str | None,
    *,
    field_name: str,
    line_no: int,
) -> int | None:
    value = clean_optional(value)
    if value is None:
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(
            f"Line {line_no}: invalid {field_name}={value!r}"
        ) from exc


def seed_metadata(
    csv_path: Path,
    *,
    apply: bool,
) -> None:
    csv_path = csv_path.resolve()

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV not found: {csv_path}"
        )

    updated_circuits = 0
    updated_layouts = 0

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        required = {
            "circuit_ref",
            "name_ko",
            "opening_year",
            "layout_ref",
            "length_meters",
            "corners",
        }

        if not reader.fieldnames:
            raise ValueError("CSV has no header")

        missing = required - set(reader.fieldnames)

        if missing:
            raise ValueError(
                "Missing CSV columns: "
                + ", ".join(sorted(missing))
            )

        with SessionLocal() as db:
            try:
                for line_no, row in enumerate(
                    reader,
                    start=2,
                ):
                    circuit_ref = row["circuit_ref"].strip()
                    layout_ref = row["layout_ref"].strip()

                    if not circuit_ref:
                        raise ValueError(
                            f"Line {line_no}: circuit_ref is empty"
                        )

                    if not layout_ref:
                        raise ValueError(
                            f"Line {line_no}: layout_ref is empty"
                        )

                    name_ko = clean_optional(
                        row.get("name_ko")
                    )
                    opening_year = clean_optional_int(
                        row.get("opening_year"),
                        field_name="opening_year",
                        line_no=line_no,
                    )
                    length_meters = clean_optional_int(
                        row.get("length_meters"),
                        field_name="length_meters",
                        line_no=line_no,
                    )
                    corners = clean_optional_int(
                        row.get("corners"),
                        field_name="corners",
                        line_no=line_no,
                    )

                    circuit = db.scalar(
                        select(Circuit).where(
                            Circuit.circuit_ref == circuit_ref
                        )
                    )

                    if circuit is None:
                        raise ValueError(
                            f"Line {line_no}: unknown circuit_ref "
                            f"{circuit_ref!r}"
                        )

                    layout = db.scalar(
                        select(CircuitLayout).where(
                            CircuitLayout.layout_ref == layout_ref
                        )
                    )

                    if layout is None:
                        raise ValueError(
                            f"Line {line_no}: unknown layout_ref "
                            f"{layout_ref!r}"
                        )

                    if layout.circuit_id != circuit.id:
                        raise ValueError(
                            f"Line {line_no}: layout_ref {layout_ref!r} "
                            f"does not belong to circuit_ref {circuit_ref!r}"
                        )

                    circuit_changed = False
                    layout_changed = False

                    if (
                        name_ko is not None
                        and circuit.name_ko != name_ko
                    ):
                        circuit.name_ko = name_ko
                        circuit_changed = True

                    if (
                        opening_year is not None
                        and circuit.opening_year != opening_year
                    ):
                        circuit.opening_year = opening_year
                        circuit_changed = True

                    if (
                        length_meters is not None
                        and circuit.length_meters != length_meters
                    ):
                        circuit.length_meters = length_meters
                        circuit_changed = True

                    if (
                        length_meters is not None
                        and layout.length_meters != length_meters
                    ):
                        layout.length_meters = length_meters
                        layout_changed = True

                    if (
                        corners is not None
                        and layout.corners != corners
                    ):
                        layout.corners = corners
                        layout_changed = True

                    if circuit_changed:
                        updated_circuits += 1
                    if layout_changed:
                        updated_layouts += 1

                    db.flush()

                    parts = []
                    if circuit_changed:
                        parts.append("CIRCUIT")
                    if layout_changed:
                        parts.append("LAYOUT")
                    action = "+".join(parts) if parts else "NOCHANGE"

                    print(
                        f"{action:<14} "
                        f"{circuit_ref:<20} "
                        f"{layout_ref:<28} "
                        f"name_ko={name_ko!r} "
                        f"opening={opening_year!r} "
                        f"length={length_meters!r} "
                        f"corners={corners!r}"
                    )

                print()
                print(f"updated circuits : {updated_circuits}")
                print(f"updated layouts  : {updated_layouts}")

                if apply:
                    db.commit()
                    print()
                    print("Changes committed.")
                else:
                    db.rollback()
                    print()
                    print("DRY RUN: no changes committed.")

            except Exception:
                db.rollback()
                raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed circuit metadata from CSV"
    )

    parser.add_argument(
        "csv",
        type=Path,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Commit changes. Without this option "
            "the command is dry-run."
        ),
    )

    args = parser.parse_args()

    seed_metadata(
        args.csv,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()
