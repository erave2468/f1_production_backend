from __future__ import annotations

from pathlib import Path

import boto3

from app.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.media_s3_region,
    )


def upload_file(
    file_path: str | Path,
    storage_key: str,
    content_type: str | None = None,
) -> str:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Media file not found: {path}"
        )

    extra_args = {}

    if content_type:
        extra_args["ContentType"] = content_type

    s3 = get_s3_client()

    s3.upload_file(
        str(path),
        settings.media_s3_bucket,
        storage_key,
        ExtraArgs=extra_args,
    )

    return storage_key


def object_exists(storage_key: str) -> bool:
    s3 = get_s3_client()

    try:
        s3.head_object(
            Bucket=settings.media_s3_bucket,
            Key=storage_key,
        )
        return True

    except s3.exceptions.ClientError as exc:
        error_code = exc.response.get(
            "Error", {}
        ).get("Code")

        if error_code in {"404", "NoSuchKey"}:
            return False

        raise


def generate_download_url(
    storage_key: str,
    *,
    expires_in: int = 300,
) -> str:
    s3 = get_s3_client()

    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.media_s3_bucket,
            "Key": storage_key,
        },
        ExpiresIn=expires_in,
    )