from __future__ import annotations

from pathlib import Path

import boto3
from botocore.config import Config

from app.config import settings


def get_s3_client():
    region = settings.media_s3_region

    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=(
            f"https://s3.{region}.amazonaws.com"
        ),
        config=Config(
            signature_version="s3v4",
            s3={
                "addressing_style": "virtual",
            },
        ),
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

    extra_args = {
        "CacheControl": ("private, max-age=86400"),
    }

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