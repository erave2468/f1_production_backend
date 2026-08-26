from __future__ import annotations

import argparse
import csv
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.media_storage import upload_file
from app.models import Country, MediaAsset


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
) -> str:
    suffix = file_path.suffix.lower()

    if asset_type == "country":
        return f"countries/{key.upper()}{suffix}"

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