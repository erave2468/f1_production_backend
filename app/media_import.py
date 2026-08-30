from __future__ import annotations

import argparse
import csv
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.media_storage import upload_file
from app.models import (
    CircuitLayout,
    Constructor,
    Country,
    Driver,
    MediaAsset,
    SeasonConstructorEntry,
    SeasonDriverEntry,
    CircuitMedia,
)


def resolve_file(
    manifest_path: Path,
    file_value: str,
) -> Path:
    path = Path(file_value)

    if not path.is_absolute():
        path = manifest_path.parent / path

    return path.resolve()


def build_storage_key(
    asset_type: str,
    key: str,
    file_path: Path,
    season: int | None = None,
    variant: str | None = None,
) -> str:
    suffix = file_path.suffix.lower()

    if asset_type == "country":
        return f"countries/{key.upper()}{suffix}"

    if asset_type == "driver":
        if season is None:
            raise ValueError(
                "Driver asset requires season"
            )

        return (
            f"drivers/{season}/"
            f"{key.upper()}{suffix}"
        )
    
    if asset_type == "constructor":
        if season is None:
            raise ValueError(
                "Constructor asset requires season"
            )

        return (
            f"constructors/{season}/"
            f"{key.lower()}{suffix}"
        )
    if asset_type == "circuit":
        image_variant = (
            variant
            or "map"
        ).strip().lower()

        return (
            f"circuits/"
            f"{key.lower()}/"
            f"{image_variant}"
            f"{suffix}"
        )
    raise ValueError(
        f"Unsupported asset type: {asset_type}"
    )

def find_country(
    db,
    country_code: str,
) -> Country | None:
    return db.scalar(
        select(Country)
        .where(
            Country.code == country_code.upper()
        )
    )


def import_country(
    db,
    *,
    manifest_path: Path,
    row: dict[str, str],
    dry_run: bool,
) -> bool:
    country_code = row["key"].strip().upper()

    country = find_country(
        db,
        country_code,
    )

    if country is None:
        print(
            f"ERROR country {country_code}: "
            "country not found in DB"
        )
        return False

    file_path = resolve_file(
        manifest_path,
        row["file"].strip(),
    )

    if not file_path.is_file():
        print(
            f"ERROR country {country_code}: "
            f"file not found: {file_path}"
        )
        return False

    storage_key = build_storage_key(
        "country",
        country_code,
        file_path,
    )

    mime_type, _ = mimetypes.guess_type(
        file_path.name
    )

    print(
        f"OK country {country_code}"
        f" -> {country.name_en}"
        f" -> {storage_key}"
    )

    if dry_run:
        return True

    # 같은 storage_key가 있으면 재사용
    asset = db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.storage_key
            == storage_key
        )
    )

    # S3에 업로드
    upload_file(
        file_path,
        storage_key,
        mime_type,
    )

    if asset is None:
        asset = MediaAsset(
            asset_type="COUNTRY_FLAG",
            storage_key=storage_key,
            public_url=None,
            mime_type=mime_type,
            alt_text=(
                row.get("alt_text")
                or f"{country.name_en} flag"
            ),
            created_at=datetime.now(UTC).replace(
                tzinfo=None
            ),
        )

        db.add(asset)
        db.flush()

    else:
        # 동일 key에 이미 등록되어 있으면
        # 메타데이터만 최신화
        asset.mime_type = mime_type

        if row.get("alt_text"):
            asset.alt_text = row[
                "alt_text"
            ].strip()

    country.flag_image_id = asset.id

    db.commit()

    print(
        f"   media_asset_id={asset.id}, "
        f"flag_image_id={country.flag_image_id}"
    )

    return True

def import_driver(
    db,
    *,
    manifest_path: Path,
    row: dict[str, str],
    dry_run: bool,
) -> bool:
    abbreviation = (
        row["key"]
        .strip()
        .upper()
    )

    season_text = (
        row.get("season")
        or ""
    ).strip()

    if not season_text:
        print(
            f"ERROR driver {abbreviation}: "
            "season is required"
        )
        return False

    try:
        season = int(season_text)

    except ValueError:
        print(
            f"ERROR driver {abbreviation}: "
            f"invalid season {season_text}"
        )
        return False

    driver = db.scalar(
        select(Driver)
        .where(
            Driver.abbreviation
            == abbreviation
        )
    )

    if driver is None:
        print(
            f"ERROR driver {abbreviation}: "
            "driver not found in DB"
        )
        return False

    entries = db.scalars(
        select(SeasonDriverEntry)
        .where(
            SeasonDriverEntry.season_year
            == season,
            SeasonDriverEntry.driver_id
            == driver.id,
        )
    ).all()

    if not entries:
        print(
            f"ERROR driver {abbreviation}: "
            f"no season entry for {season}"
        )
        return False

    file_path = resolve_file(
        manifest_path,
        row["file"].strip(),
    )

    if not file_path.is_file():
        print(
            f"ERROR driver {abbreviation}: "
            f"file not found: {file_path}"
        )
        return False

    storage_key = build_storage_key(
        "driver",
        abbreviation,
        file_path,
        season,
    )

    mime_type, _ = mimetypes.guess_type(
        file_path.name
    )

    print(
        f"OK driver {abbreviation}"
        f" -> {driver.full_name}"
        f" ({season})"
        f" -> {storage_key}"
    )

    if dry_run:
        return True

    asset = db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.storage_key
            == storage_key
        )
    )

    upload_file(
        file_path,
        storage_key,
        mime_type,
    )

    if asset is None:
        asset = MediaAsset(
            asset_type="DRIVER_PORTRAIT",
            storage_key=storage_key,
            public_url=None,
            mime_type=mime_type,
            alt_text=(
                row.get("alt_text")
                or driver.full_name
            ),
            created_at=datetime.now(
                UTC
            ).replace(
                tzinfo=None
            ),
        )

        db.add(asset)
        db.flush()

    else:
        asset.mime_type = mime_type

        if row.get("alt_text"):
            asset.alt_text = (
                row["alt_text"]
                .strip()
            )

    # 같은 시즌에 팀을 옮겼더라도
    # 해당 드라이버의 모든 시즌 엔트리에
    # 같은 portrait를 연결
    for entry in entries:
        entry.portrait_image_id = asset.id

    db.commit()

    print(
        f"   media_asset_id={asset.id}, "
        f"updated_entries={len(entries)}"
    )

    return True

def import_constructor(
    db,
    *,
    manifest_path: Path,
    row: dict[str, str],
    dry_run: bool,
) -> bool:
    constructor_ref = (
        row["key"]
        .strip()
        .lower()
    )

    season_text = (
        row.get("season")
        or ""
    ).strip()

    if not season_text:
        print(
            f"ERROR constructor "
            f"{constructor_ref}: "
            "season is required"
        )
        return False

    try:
        season = int(season_text)

    except ValueError:
        print(
            f"ERROR constructor "
            f"{constructor_ref}: "
            f"invalid season {season_text}"
        )
        return False

    # constructor_ref를 기준으로
    # 안정적으로 팀 검색
    constructor = db.scalar(
        select(Constructor)
        .where(
            Constructor.constructor_ref
            == constructor_ref
        )
    )

    if constructor is None:
        print(
            f"ERROR constructor "
            f"{constructor_ref}: "
            "constructor not found in DB"
        )
        return False

    entry = db.scalar(
        select(SeasonConstructorEntry)
        .where(
            SeasonConstructorEntry.season_year
            == season,
            SeasonConstructorEntry.constructor_id
            == constructor.id,
        )
    )

    if entry is None:
        print(
            f"ERROR constructor "
            f"{constructor_ref}: "
            f"no season entry for {season}"
        )
        return False

    file_path = resolve_file(
        manifest_path,
        row["file"].strip(),
    )

    if not file_path.is_file():
        print(
            f"ERROR constructor "
            f"{constructor_ref}: "
            f"file not found: {file_path}"
        )
        return False

    storage_key = build_storage_key(
        "constructor",
        constructor_ref,
        file_path,
        season,
    )

    mime_type, _ = mimetypes.guess_type(
        file_path.name
    )

    print(
        f"OK constructor "
        f"{constructor_ref}"
        f" -> {constructor.name}"
        f" ({season})"
        f" -> {storage_key}"
    )

    if dry_run:
        return True

    asset = db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.storage_key
            == storage_key
        )
    )

    upload_file(
        file_path,
        storage_key,
        mime_type,
    )

    if asset is None:
        asset = MediaAsset(
            asset_type="CONSTRUCTOR_LOGO",
            storage_key=storage_key,
            public_url=None,
            mime_type=mime_type,
            alt_text=(
                (row.get("alt_text") or "").strip()
                or f"{constructor.name} logo"
            ),
            created_at=datetime.now(
                UTC
            ).replace(
                tzinfo=None
            ),
        )

        db.add(asset)
        db.flush()

    else:
        asset.mime_type = mime_type

        if row.get("alt_text"):
            asset.alt_text = (
                row["alt_text"]
                .strip()
            )

    entry.logo_image_id = asset.id

    db.commit()

    print(
        f"   media_asset_id={asset.id}, "
        f"logo_image_id={entry.logo_image_id}"
    )

    return True

def import_circuit(
    db,
    *,
    manifest_path: Path,
    row: dict[str, str],
    dry_run: bool,
) -> bool:
    layout_ref = (
        row["key"]
        .strip()
        .lower()
    )
    image_type = (
        (row.get("variant") or "MAP")
        .strip()
        .upper()
    )

    display_order = int(
        row.get("display_order")
        or 0
    )
    # layout_ref 기준으로
    # 정확한 CircuitLayout 검색
    layout = db.scalar(
        select(CircuitLayout)
        .where(
            CircuitLayout.layout_ref
            == layout_ref
        )
    )

    if layout is None:
        print(
            f"ERROR circuit "
            f"{layout_ref}: "
            "circuit layout not found in DB"
        )
        return False

    file_path = resolve_file(
        manifest_path,
        row["file"].strip(),
    )

    if not file_path.is_file():
        print(
            f"ERROR circuit "
            f"{layout_ref}: "
            f"file not found: {file_path}"
        )
        return False

    storage_key = build_storage_key(
        "circuit",
        layout_ref,
        file_path,
        variant=image_type,
    )

    mime_type, _ = mimetypes.guess_type(
        file_path.name
    )

    print(
        f"OK circuit "
        f"{layout_ref}"
        f" -> {layout.layout_name}"
        f" -> {storage_key}"
    )

    if dry_run:
        return True

    asset = db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.storage_key
            == storage_key
        )
    )

    # S3 업로드
    upload_file(
        file_path,
        storage_key,
        mime_type,
    )

    if asset is None:
        asset = MediaAsset(
            asset_type=(
                f"CIRCUIT_{image_type}"
            ),
            storage_key=storage_key,
            public_url=None,
            mime_type=mime_type,
            alt_text=(
                (row.get("alt_text") or "").strip()
                or (
                    f"{layout.layout_name} "
                    "layout"
                )
            ),
            created_at=datetime.now(
                UTC
            ).replace(
                tzinfo=None
            ),
        )

        db.add(asset)
        db.flush()

    else:
        asset.mime_type = mime_type

        if row.get("alt_text"):
            asset.alt_text = (
                row["alt_text"]
                .strip()
            )

    # 핵심 연결
    link = db.scalar(
        select(CircuitMedia)
        .where(
            CircuitMedia.circuit_layout_id
            == layout.id,

            CircuitMedia.media_asset_id
            == asset.id,
        )
    )

    if link is None:
        link = CircuitMedia(
            circuit_layout_id=layout.id,
            media_asset_id=asset.id,
            image_type=image_type,
            display_order=display_order,
        )

        db.add(link)

    else:
        link.image_type = image_type
        link.display_order = display_order


    # 대표 MAP인 경우에만
    # 기존 필드도 업데이트
    if image_type == "MAP":
        layout.map_image_id = asset.id


    db.commit()

    print(
        f"   media_asset_id={asset.id}, "
        f"map_image_id={layout.map_image_id}"
    )

    return True

def import_manifest(
    manifest_path: Path,
    dry_run: bool,
) -> None:
    manifest_path = manifest_path.resolve()

    success = 0
    failed = 0

    with manifest_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        required = {
            "type",
            "key",
            "file",
        }

        if not reader.fieldnames:
            raise ValueError(
                "Manifest has no header"
            )

        missing = (
            required
            - set(reader.fieldnames)
        )

        if missing:
            raise ValueError(
                "Missing manifest columns: "
                + ", ".join(sorted(missing))
            )

        with SessionLocal() as db:
            for row in reader:
                asset_type = (
                    row["type"]
                    .strip()
                    .lower()
                )

                try:
                    if asset_type == "country":
                        ok = import_country(
                            db,
                            manifest_path=manifest_path,
                            row=row,
                            dry_run=dry_run,
                        )

                    elif asset_type == "driver":
                        ok = import_driver(
                            db,
                            manifest_path=manifest_path,
                            row=row,
                            dry_run=dry_run,
                        )
                    elif asset_type == "constructor":
                        ok = import_constructor(
                            db,
                            manifest_path=manifest_path,
                            row=row,
                            dry_run=dry_run,
                        )
                    elif asset_type == "circuit":
                        ok = import_circuit(
                            db,
                            manifest_path=manifest_path,
                            row=row,
                            dry_run=dry_run,
                        )
                    else:
                        print(
                            "ERROR unsupported type: "
                            f"{asset_type}"
                        )
                        ok = False

                except Exception as exc:
                    db.rollback()

                    print(
                        f"ERROR {asset_type} "
                        f"{row.get('key')}: {exc}"
                    )

                    ok = False

                if ok:
                    success += 1
                else:
                    failed += 1

    print()
    print("Import result")
    print(f"  success: {success}")
    print(f"  failed : {failed}")

    if dry_run:
        print("  mode   : DRY RUN")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import F1 media into "
            "S3 and RDS"
        )
    )

    parser.add_argument(
        "manifest",
        type=Path,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Check DB/file matching "
            "without uploading or updating DB"
        ),
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    import_manifest(
        args.manifest,
        args.dry_run,
    )


if __name__ == "__main__":
    main()