from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.media_storage import (
    generate_download_url,
    object_exists,
)
from app.models import MediaAsset


router = APIRouter(
    prefix="/media",
    tags=["media"],
)

Db = Annotated[
    Session,
    Depends(get_db),
]


@router.get(
    "/{image_id}",
    include_in_schema=False,
)
def get_media(
    image_id: int,
    db: Db,
):
    asset = db.get(
        MediaAsset,
        image_id,
    )

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media asset not found",
        )

    if not object_exists(
        asset.storage_key
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found in storage",
        )

    url = generate_download_url(
        asset.storage_key,
        expires_in=300,
    )

    return RedirectResponse(
        url=url,
        status_code=307,
    )