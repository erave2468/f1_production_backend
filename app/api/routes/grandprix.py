from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import services
from app.api.schemas import (
    GrandPrixDetailResponse,
    GrandPrixHistoryResponse,
    GrandPrixListItem,
    GrandPrixListResponse,
    GrandPrixOverviewResponse,
    GrandPrixResponse,
    GrandPrixResultResponse,
)
from app.db import get_db
from app.models import SessionType

router = APIRouter(prefix="/grandprix", tags=["grandprix"])
Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=GrandPrixListResponse)
def grand_prix_list(
    db: Db,
    season: Annotated[int | None, Query(ge=1950, le=2100)] = None,
) -> GrandPrixListResponse:
    return GrandPrixListResponse(grandprix=services.list_grand_prix(db, season))


'''@router.get("/next", response_model=GrandPrixListItem)
def next_grand_prix(
    db: Db,
    season: Annotated[int | None, Query(ge=1950, le=2100)] = None,
) -> GrandPrixListItem:
    return services.get_next_grand_prix(db, season)'''

'''@router.get("/last", response_model=GrandPrixListItem)
def last_grand_prix(
    db: Db,
    season: Annotated[int | None, Query(ge=1950, le=2100)] = None,
) -> GrandPrixListItem:
    return services.get_last_grand_prix(db, season)'''

@router.get("/recent")
def recent_grand_prix(
    db: Db,
    season: Annotated[int | None, Query(ge=1950, le=2100)] = None,
):
    return services.get_next_last_current_grand_prix(db, season)

@router.get("/{grand_prix_id}", response_model=GrandPrixResponse)
def grand_prix(grand_prix_id: int, db: Db) -> GrandPrixResponse:
    return services.get_grand_prix(db, grand_prix_id)

@router.get("/{grand_prix_id}/overview", response_model=GrandPrixOverviewResponse)
def grand_prix_overview(grand_prix_id: int, db: Db) -> GrandPrixOverviewResponse:
    return services.get_grand_prix_overview(db, grand_prix_id)


@router.get("/{grand_prix_id}/result", response_model=GrandPrixResultResponse)
def grand_prix_result(grand_prix_id: int, db: Db) -> GrandPrixResultResponse:
    return services.get_grand_prix_result(db, grand_prix_id)


@router.get("/{grand_prix_id}/history", response_model=GrandPrixHistoryResponse)
def grand_prix_history(
    grand_prix_id: int,
    db: Db,
    session: Annotated[SessionType, Query(description="FP1, FP2, FP3, Q, SQ, S, R")] = SessionType.R,
) -> GrandPrixHistoryResponse:
    return services.get_grand_prix_history(db, grand_prix_id, session)


@router.get("/{grand_prix_id}/detail", response_model=GrandPrixDetailResponse)
def grand_prix_detail(
    grand_prix_id: int,
    db: Db,
    session: Annotated[SessionType, Query(description="FP1, FP2, FP3, Q, SQ, S, R")] = SessionType.R,
) -> GrandPrixDetailResponse:
    return GrandPrixDetailResponse(
        driver=services.get_grand_prix_detail(db, grand_prix_id, session)
    )
