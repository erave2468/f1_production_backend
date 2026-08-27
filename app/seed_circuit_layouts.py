from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Circuit, CircuitLayout, GrandPrix


def seed_layouts(
    year: int,
    *,
    apply: bool,
) -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                GrandPrix,
                Circuit,
            )
            .join(
                Circuit,
                Circuit.id == GrandPrix.circuit_id,
            )
            .where(
                GrandPrix.season_year == year
            )
            .order_by(
                GrandPrix.round_number
            )
        ).all()

        created = 0
        reused = 0
        linked = 0

        for gp, circuit in rows:
            # 최초 기준 레이아웃.
            # 이후 실제 레이아웃 변경이 발생하면
            # 새로운 layout_ref를 만들어 관리하면 됨.
            layout_ref = (
                f"{circuit.circuit_ref}_{year}"
            )

            layout = db.scalar(
                select(CircuitLayout)
                .where(
                    CircuitLayout.layout_ref
                    == layout_ref
                )
            )

            if layout is None:
                print(
                    f"CREATE R{gp.round_number:02d} "
                    f"{circuit.circuit_ref} "
                    f"-> {layout_ref}"
                )

                layout = CircuitLayout(
                    circuit_id=circuit.id,
                    layout_ref=layout_ref,
                    layout_name=circuit.name,
                    valid_from_year=year,
                    valid_to_year=None,

                    # circuits에 기존 길이 데이터가
                    # 있으면 우선 복사
                    length_meters=circuit.length_meters,

                    corners=None,
                    map_image_id=None,
                    is_current=True,
                )

                db.add(layout)
                db.flush()

                created += 1

            else:
                print(
                    f"REUSE  R{gp.round_number:02d} "
                    f"{circuit.circuit_ref} "
                    f"-> {layout.layout_ref}"
                )

                reused += 1

            if gp.circuit_layout_id != layout.id:
                print(
                    f"       GP {gp.id}: "
                    f"{gp.circuit_layout_id} "
                    f"-> {layout.id}"
                )

                gp.circuit_layout_id = layout.id
                linked += 1

        print()
        print(f"created : {created}")
        print(f"reused  : {reused}")
        print(f"linked  : {linked}")

        if apply:
            db.commit()

            print()
            print("Changes committed.")

        else:
            db.rollback()

            print()
            print(
                "DRY RUN: no changes committed."
            )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "year",
        type=int,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    args = parser.parse_args()

    seed_layouts(
        args.year,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()