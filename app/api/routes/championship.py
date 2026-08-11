from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import services
from app.api.schemas import ChampionshipConstructorResponse, ChampionshipDriverResponse
from app.db import get_db

router = APIRouter(prefix="/championship", tags=["championship"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/driver", response_model=ChampionshipDriverResponse)
def driver_championship(
    db: Db,
    season: Annotated[int | None, Query(ge=1950, le=2100)] = None,
    after_round: Annotated[int | None, Query(ge=1, le=40)] = None,
) -> ChampionshipDriverResponse:
    return ChampionshipDriverResponse(
        driver=services.get_driver_championship(db, season, after_round)
    )


@router.get("/constructor", response_model=ChampionshipConstructorResponse)
def constructor_championship(
    db: Db,
    season: Annotated[int | None, Query(ge=1950, le=2100)] = None,
    after_round: Annotated[int | None, Query(ge=1, le=40)] = None,
) -> ChampionshipConstructorResponse:
    return ChampionshipConstructorResponse(
        team=services.get_constructor_championship(db, season, after_round)
    )


# Compatibility alias for the original frontend draft.
@router.get("/construct", response_model=ChampionshipConstructorResponse, include_in_schema=False)
def construct_championship_alias(
    db: Db,
    season: Annotated[int | None, Query(ge=1950, le=2100)] = None,
    after_round: Annotated[int | None, Query(ge=1, le=40)] = None,
) -> ChampionshipConstructorResponse:
    return ChampionshipConstructorResponse(
        team=services.get_constructor_championship(db, season, after_round)
    )
