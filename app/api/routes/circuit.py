from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import services
from app.api.schemas import CircuitResponse, CircuitGrandPrixResponse
from app.db import get_db

router = APIRouter(prefix="/circuit", tags=["circuit"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/{circuit_id}", response_model=CircuitResponse)
def circuit(circuit_id: int, db: Db) -> CircuitResponse:
    return services.get_circuit(db, circuit_id)

@router.get(
    "/{circuit_id}/grandprix",
    response_model=CircuitGrandPrixResponse,
)
def circuit_grand_prix(
    circuit_id: int,
    db: Db,
) -> CircuitGrandPrixResponse:
    return services.get_circuit_grand_prix(
        db,
        circuit_id,
    )