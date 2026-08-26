from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel

from app.models import SessionType


class GrandPrixListItem(BaseModel):
    grandprix_id: int
    is_current: bool
    is_next: bool
    name: str
    round: int
    nation_flag_image_id: int | None = None
    first_driver_id: int | None = None
    first_driver_image_id: int | None = None
    date: datetime | None = None


class GrandPrixListResponse(BaseModel):
    grandprix: list[GrandPrixListItem]


class GrandPrixResponse(BaseModel):
    name: str
    round: int
    circuit_name: str
    circuit_id: int
    nation_flag_image_id: int | None = None
    is_sprint: bool


class ScheduleItem(BaseModel):
    session_code: SessionType
    time: datetime | None


class WeatherItem(BaseModel):
    session_code: SessionType
    temperature: float | None
    rainfall: bool | None = None


class TireOverviewItem(BaseModel):
    tire_code: int
    tire_type: str | None = None
    tire_set: int | None = None


class CircuitOverview(BaseModel):
    circuit_korean_name: str | None = None
    circuit_english_name: str
    circuit_region_name: str | None = None
    circuit_image_id: int | None = None
    circuit_laps: int | None = None
    circuit_one_lap_length: float | None = None
    circuit_total_length: float | None = None


class GrandPrixOverviewResponse(BaseModel):
    schedule: list[ScheduleItem]
    weather: list[WeatherItem]
    tire: list[TireOverviewItem]
    circuit: CircuitOverview


class GrandPrixResultDriver(BaseModel):
    driver_id: int
    name: str
    teamname: str
    team_image_id: int | None = None
    position: int | None = None
    points: float | None = None
    rank_change: int = 0
    racetime: str | None = None


class DotdResponse(BaseModel):
    driver_id: int
    dotd_image_id: int | None = None
    starting_grid: int | None = None


class GrandPrixResultResponse(BaseModel):
    driver: list[GrandPrixResultDriver]
    dotd: DotdResponse | None = None


class HistoryFlag(BaseModel):
    flag_type: str
    startlap: int | None = None
    endlap: int | None = None


class HistoryLap(BaseModel):
    lap_number: int
    position: int | None = None
    laptime: str | None = None
    gaptime: float | None = None


class TireStintResponse(BaseModel):
    tire_type: str | None = None
    startlap: int
    endlap: int


class HistoryDriver(BaseModel):
    driver_id: int
    name: str
    team: str
    team_image_id: int | None = None
    driver_color: str | None = None
    laps: list[HistoryLap]
    tire: list[TireStintResponse]


class GrandPrixHistoryResponse(BaseModel):
    flags: list[HistoryFlag]
    driver: list[HistoryDriver]


class GrandPrixDetailDriver(BaseModel):
    driver_id: int
    name: str
    team_image_id: int | None = None
    team_color: str | None = None
    racetime: str | None = None
    position: int | None = None
    fastestlap: str | None = None
    speedtrap: float | None = None
    is_completed: bool
    tire: list[TireStintResponse]
    theoretical_lap_time: str | None = None
    sector1_time: str | None = None
    sector2_time: str | None = None
    sector3_time: str | None = None
    lap_amount: int | None = None
    points: float | None = None


class GrandPrixDetailResponse(BaseModel):
    driver: list[GrandPrixDetailDriver]


class ChampionshipDriverItem(BaseModel):
    driver_id: int
    name: str
    teamname: str
    team_image_id: int | None = None
    points: float
    rank_change: int = 0


class ChampionshipDriverResponse(BaseModel):
    driver: list[ChampionshipDriverItem]


class ChampionshipConstructorItem(BaseModel):
    team_id: int
    team_name: str
    team_image_id: int | None = None
    points: float
    rank_change: int = 0


class ChampionshipConstructorResponse(BaseModel):
    team: list[ChampionshipConstructorItem]


class CircuitRecordItem(BaseModel):
    record_type: str
    driver_id: int | None = None
    driver_name: str | None = None
    record_year: int | None = None
    driver_team: str | None = None
    record_time: str | None = None


class CircuitResponse(BaseModel):
    circuit_korean_name: str | None = None
    circuit_english_name: str
    circuit_image_id: int | None = None
    circuit_one_lap_length: float | None = None
    circuit_corners: int | None = None
    circuit_opening_year: int | None = None
    record: list[CircuitRecordItem]
