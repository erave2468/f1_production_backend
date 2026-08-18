from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.schemas import (
    ChampionshipConstructorItem,
    ChampionshipDriverItem,
    CircuitOverview,
    CircuitRecordItem,
    CircuitResponse,
    DotdResponse,
    GrandPrixDetailDriver,
    GrandPrixHistoryResponse,
    GrandPrixListItem,
    GrandPrixOverviewResponse,
    GrandPrixResponse,
    GrandPrixResultDriver,
    GrandPrixResultResponse,
    HistoryDriver,
    HistoryFlag,
    HistoryLap,
    ScheduleItem,
    TireOverviewItem,
    TireStintResponse,
    WeatherItem,
)
from app.models import (
    Circuit,
    CircuitLayout,
    CircuitRecord,
    Constructor,
    ConstructorStanding,
    Country,
    Driver,
    DriverOfTheDay,
    DriverStanding,
    GrandPrix,
    GrandPrixTyreAllocation,
    Lap,
    RacePeriod,
    Season,
    SeasonConstructorEntry,
    SeasonDriverEntry,
    SessionEntry,
    SessionModel,
    SessionResult,
    SessionType,
    TyreStint,
    WeatherSample,
)


TYRE_ROLE_CODE = {
    "HARD": 1,
    "MEDIUM": 2,
    "SOFT": 3,
    "INTERMEDIATE": 4,
    "INTER": 4,
    "WET": 5,
}


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _float(value: Decimal | int | float | None) -> float | None:
    return None if value is None else float(value)


def _duration(us: int | None) -> str | None:
    if us is None:
        return None
    milliseconds = us // 1000
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def _gap_seconds(us: int | None) -> float | None:
    return None if us is None else round(us / 1_000_000, 3)


def resolve_season(db: Session, season: int | None) -> int:
    if season is not None:
        if db.scalar(select(Season.year).where(Season.year == season)) is None:
            raise _not_found(f"Season {season} not found")
        return season
    latest = db.scalar(select(func.max(Season.year)))
    if latest is None:
        raise _not_found("No season data found")
    return int(latest)


def _get_gp(db: Session, grand_prix_id: int) -> GrandPrix:
    gp = db.get(GrandPrix, grand_prix_id)
    if gp is None:
        raise _not_found("Grand Prix not found")
    return gp


def _get_session(db: Session, grand_prix_id: int, session_type: SessionType) -> SessionModel:
    row = db.scalar(
        select(SessionModel).where(
            SessionModel.grand_prix_id == grand_prix_id,
            SessionModel.type == session_type,
        )
    )
    if row is None:
        raise _not_found(f"Session {session_type.value} not found for this Grand Prix")
    return row


def _country_flag_id(db: Session, country_code: str | None) -> int | None:
    if not country_code:
        return None
    return db.scalar(select(Country.flag_image_id).where(Country.code == country_code))


def _driver_portrait_id(
    db: Session,
    season: int,
    driver_id: int | None,
    constructor_id: int | None = None,
) -> int | None:
    if driver_id is None:
        return None
    stmt = select(SeasonDriverEntry.portrait_image_id).where(
        SeasonDriverEntry.season_year == season,
        SeasonDriverEntry.driver_id == driver_id,
    )
    if constructor_id is not None:
        stmt = stmt.where(SeasonDriverEntry.constructor_id == constructor_id)
    return db.scalar(stmt.limit(1))


def _team_meta(db: Session, season: int, constructor_id: int) -> tuple[int | None, str | None]:
    row = db.execute(
        select(SeasonConstructorEntry.logo_image_id, SeasonConstructorEntry.color).where(
            SeasonConstructorEntry.season_year == season,
            SeasonConstructorEntry.constructor_id == constructor_id,
        )
    ).first()
    return (row[0], row[1]) if row else (None, None)


def _layout_for_gp(db: Session, gp: GrandPrix) -> CircuitLayout | None:
    if gp.circuit_layout_id:
        layout = db.get(CircuitLayout, gp.circuit_layout_id)
        if layout:
            return layout
    return db.scalar(
        select(CircuitLayout)
        .where(CircuitLayout.circuit_id == gp.circuit_id)
        .order_by(CircuitLayout.is_current.desc(), CircuitLayout.valid_from_year.desc())
        .limit(1)
    )


def _next_grand_prix_id(db: Session, season: int) -> int | None:
    now = datetime.now(UTC).replace(tzinfo=None)
    today = now.date()
    RaceSession = aliased(SessionModel)
    return db.scalar(
        select(GrandPrix.id)
        .join(
            RaceSession,
            (RaceSession.grand_prix_id == GrandPrix.id) & (RaceSession.type == SessionType.R),
        )
        .where(
            GrandPrix.season_year == season,
            func.lower(func.coalesce(RaceSession.status, "scheduled")) != "completed",
            or_(
                RaceSession.scheduled_start >= now,
                GrandPrix.weekend_end_date >= today,
            ),
        )
        .order_by(RaceSession.scheduled_start.asc())
        .limit(1)
    )
def _last_grand_prix_id(db: Session, season: int) -> int | None:
    now = datetime.now(UTC).replace(tzinfo=None)
    today = now.date()

    RaceSession = aliased(SessionModel)

    result = db.scalar(
        select(GrandPrix.id)
        .join(
            RaceSession,
            (RaceSession.grand_prix_id == GrandPrix.id)
            & (RaceSession.type == SessionType.R),
        )
        .where(
            GrandPrix.season_year == season,
            func.lower(func.coalesce(RaceSession.status, "scheduled")) == "completed",
            or_(
                RaceSession.scheduled_start < now,
                GrandPrix.weekend_end_date < today,
            ),
        )
        .order_by(RaceSession.scheduled_start.desc())
        .limit(1)
    )

    return result

def list_grand_prix(db: Session, season: int | None) -> list[GrandPrixListItem]:
    season = resolve_season(db, season)
    RaceSession = aliased(SessionModel)
    rows = db.execute(
        select(GrandPrix, RaceSession.scheduled_start)
        .outerjoin(
            RaceSession,
            (RaceSession.grand_prix_id == GrandPrix.id) & (RaceSession.type == SessionType.R),
        )
        .where(GrandPrix.season_year == season)
        .order_by(GrandPrix.round_number)
    ).all()

    today = datetime.now(UTC).date()
    next_id = _next_grand_prix_id(db, season)
    output: list[GrandPrixListItem] = []
    for gp, race_start in rows:
        output.append(
            GrandPrixListItem(
                grandprix_id=gp.id,
                is_current=bool(
                    gp.weekend_start_date
                    and gp.weekend_end_date
                    and gp.weekend_start_date <= today <= gp.weekend_end_date
                    
                ),
                is_next=gp.id == next_id,
                name=gp.display_name_ko or gp.display_name,
                round=gp.round_number,
                nation_flag_image_id=_country_flag_id(db, gp.country_code),
                first_driver_id=gp.winning_driver_id,
                first_driver_image_id=_driver_portrait_id(
                    db,
                    gp.season_year,
                    gp.winning_driver_id,
                    gp.winning_constructor_id,
                ),
                date=race_start,
            )
        )
    return output


def get_next_grand_prix(db: Session, season: int | None) -> GrandPrixListItem:
    season = resolve_season(db, season)
    next_id = _next_grand_prix_id(db, season)
    if next_id is None:
        raise _not_found(f"No upcoming Grand Prix found for season {season}")
    return next(item for item in list_grand_prix(db, season) if item.grandprix_id == next_id)

def get_last_grand_prix(db: Session, season: int | None) -> GrandPrixListItem:
    season = resolve_season(db, season)
    last_id = _last_grand_prix_id(db, season)
    if last_id is None:
        raise _not_found(f"No last Grand Prix found for season {season}")
    return next(item for item in list_grand_prix(db, season) if item.grandprix_id == last_id)


def get_grand_prix(db: Session, grand_prix_id: int) -> GrandPrixResponse:
    gp = _get_gp(db, grand_prix_id)
    circuit = db.get(Circuit, gp.circuit_id)
    if circuit is None:
        raise _not_found("Circuit not found")
    sprint_exists = db.scalar(
        select(func.count(SessionModel.id)).where(
            SessionModel.grand_prix_id == gp.id,
            SessionModel.type.in_([SessionType.S, SessionType.SQ]),
        )
    )
    return GrandPrixResponse(
        name=gp.display_name_ko or gp.display_name,
        round=gp.round_number,
        circuit_name=circuit.name_ko or circuit.name,
        circuit_id=circuit.id,
        nation_flag_image_id=_country_flag_id(db, gp.country_code),
        is_sprint=bool(sprint_exists),
    )


def get_grand_prix_overview(db: Session, grand_prix_id: int) -> GrandPrixOverviewResponse:
    gp = _get_gp(db, grand_prix_id)
    circuit = db.get(Circuit, gp.circuit_id)
    if circuit is None:
        raise _not_found("Circuit not found")
    layout = _layout_for_gp(db, gp)

    sessions = db.scalars(
        select(SessionModel)
        .where(SessionModel.grand_prix_id == gp.id)
        .order_by(SessionModel.scheduled_start)
    ).all()
    weather_rows = db.execute(
        select(SessionModel.type, func.avg(WeatherSample.air_temperature_c))
        .outerjoin(WeatherSample, WeatherSample.session_id == SessionModel.id)
        .where(SessionModel.grand_prix_id == gp.id)
        .group_by(SessionModel.id, SessionModel.type, SessionModel.scheduled_start)
        .order_by(SessionModel.scheduled_start)
    ).all()
    tyres = db.scalars(
        select(GrandPrixTyreAllocation)
        .where(GrandPrixTyreAllocation.grand_prix_id == gp.id)
        .order_by(GrandPrixTyreAllocation.weekend_role)
    ).all()

    race_session = next((s for s in sessions if s.type == SessionType.R), None)
    lap_count = (race_session.total_laps if race_session and race_session.total_laps else gp.scheduled_laps)
    length_m = layout.length_meters if layout and layout.length_meters else circuit.length_meters
    one_lap_km = length_m / 1000 if length_m else None
    if gp.scheduled_race_distance_meters:
        total_km = gp.scheduled_race_distance_meters / 1000
    elif one_lap_km is not None and lap_count:
        total_km = one_lap_km * lap_count
    else:
        total_km = None
    
    country = db.get(Country, circuit.country_code) if circuit.country_code else None

    weather_items: list[WeatherItem] = []

    for session_row in sessions:
        # 기존과 동일하게 세션 평균 기온
        temperature = db.scalar(
            select(
                func.avg(
                    WeatherSample.air_temperature_c
                )
            )
            .where(
                WeatherSample.session_id == session_row.id
            )
        )

        # 실제 시작 시간이 있으면 actual_start를 우선 사용
        target_time = (
            session_row.actual_start
            or session_row.scheduled_start
        )

        rainfall = None

        if target_time is not None:
            rainfall = db.scalar(
                select(WeatherSample.rainfall)
                .where(
                    WeatherSample.session_id == session_row.id,
                    WeatherSample.sample_time.is_not(None),
                    WeatherSample.sample_time <= target_time,
                )
                .order_by(
                    WeatherSample.sample_time.desc()
                )
                .limit(1)
            )

        weather_items.append(
            WeatherItem(
                session_code=session_row.type,
                temperature=_float(temperature),
                rainfall=rainfall,
            )
        )
    return GrandPrixOverviewResponse(
        schedule=[ScheduleItem(session_code=s.type, time=s.scheduled_start) for s in sessions],
        weather=weather_items,
        tire=[
            TireOverviewItem(
                tire_code=TYRE_ROLE_CODE.get(t.weekend_role.upper(), 0),
                tire_type=t.compound_code,
                tire_set=t.sets_per_driver,
            )
            for t in tyres
        ],
        circuit=CircuitOverview(
            circuit_korean_name=circuit.name_ko,
            circuit_english_name=circuit.name,
            circuit_region_name=(country.name_ko or country.name_en) if country else circuit.country,
            circuit_image_id=layout.map_image_id if layout else None,
            circuit_laps=lap_count,
            circuit_one_lap_length=one_lap_km,
            circuit_total_length=round(total_km, 3) if total_km is not None else None,
        ),
    )


def _latest_round(db: Session, season: int, table: type[DriverStanding] | type[ConstructorStanding]) -> int:
    value = db.scalar(select(func.max(table.after_round)).where(table.season_year == season))
    if value is None:
        raise _not_found(f"No championship standings found for season {season}")
    return int(value)


def _driver_rank_changes(db: Session, season: int, after_round: int) -> dict[int, int]:
    current = dict(db.execute(select(DriverStanding.driver_id, DriverStanding.position).where(
        DriverStanding.season_year == season, DriverStanding.after_round == after_round)).all())
    previous = dict(db.execute(select(DriverStanding.driver_id, DriverStanding.position).where(
        DriverStanding.season_year == season, DriverStanding.after_round == after_round - 1)).all()) if after_round > 1 else {}
    return {driver_id: previous.get(driver_id, pos) - pos for driver_id, pos in current.items()}


def _constructor_rank_changes(db: Session, season: int, after_round: int) -> dict[int, int]:
    current = dict(db.execute(select(ConstructorStanding.constructor_id, ConstructorStanding.position).where(
        ConstructorStanding.season_year == season, ConstructorStanding.after_round == after_round)).all())
    previous = dict(db.execute(select(ConstructorStanding.constructor_id, ConstructorStanding.position).where(
        ConstructorStanding.season_year == season, ConstructorStanding.after_round == after_round - 1)).all()) if after_round > 1 else {}
    return {constructor_id: previous.get(constructor_id, pos) - pos for constructor_id, pos in current.items()}


def get_grand_prix_result(db: Session, grand_prix_id: int) -> GrandPrixResultResponse:
    gp = _get_gp(db, grand_prix_id)
    race = _get_session(db, gp.id, SessionType.R)
    rank_changes = _driver_rank_changes(db, gp.season_year, gp.round_number)
    rows = db.execute(
        select(SessionEntry, SessionResult, Driver, Constructor)
        .join(SessionResult, SessionResult.session_entry_id == SessionEntry.id)
        .join(Driver, Driver.id == SessionEntry.driver_id)
        .join(Constructor, Constructor.id == SessionEntry.constructor_id)
        .where(SessionEntry.session_id == race.id)
        .order_by(SessionResult.finishing_position, SessionEntry.id)
    ).all()

    drivers: list[GrandPrixResultDriver] = []
    for entry, result, driver, constructor in rows:
        logo_id, _ = _team_meta(db, gp.season_year, constructor.id)
        drivers.append(GrandPrixResultDriver(
            driver_id=driver.id,
            name=driver.full_name,
            teamname=constructor.name,
            team_image_id=logo_id,
            points=_float(result.points),
            rank_change=rank_changes.get(driver.id, 0),
            racetime=_duration(result.total_time_us),
        ))

    dotd_row = db.execute(
        select(DriverOfTheDay, SessionEntry)
        .outerjoin(SessionEntry, (SessionEntry.session_id == race.id) & (SessionEntry.driver_id == DriverOfTheDay.driver_id))
        .where(DriverOfTheDay.grand_prix_id == gp.id)
    ).first()
    dotd = None
    if dotd_row:
        entity, race_entry = dotd_row
        dotd = DotdResponse(
            driver_id=entity.driver_id,
            dotd_image_id=_driver_portrait_id(db, gp.season_year, entity.driver_id),
            starting_grid=race_entry.grid_position if race_entry else None,
        )
    return GrandPrixResultResponse(driver=drivers, dotd=dotd)


def get_grand_prix_history(db: Session, grand_prix_id: int, session_type: SessionType) -> GrandPrixHistoryResponse:
    gp = _get_gp(db, grand_prix_id)
    session_row = _get_session(db, gp.id, session_type)
    periods = db.scalars(
        select(RacePeriod).where(RacePeriod.session_id == session_row.id).order_by(RacePeriod.start_lap, RacePeriod.start_time_us)
    ).all()
    flags = [HistoryFlag(flag_type=p.period_type, startlap=p.start_lap, endlap=p.end_lap) for p in periods]

    rows = db.execute(
        select(SessionEntry, Driver, Constructor)
        .join(Driver, Driver.id == SessionEntry.driver_id)
        .join(Constructor, Constructor.id == SessionEntry.constructor_id)
        .where(SessionEntry.session_id == session_row.id)
        .order_by(SessionEntry.id)
    ).all()
    output: list[HistoryDriver] = []
    for entry, driver, constructor in rows:
        logo_id, color = _team_meta(db, gp.season_year, constructor.id)
        laps = db.scalars(select(Lap).where(Lap.session_entry_id == entry.id).order_by(Lap.lap_number)).all()
        stints = db.scalars(select(TyreStint).where(TyreStint.session_entry_id == entry.id).order_by(TyreStint.stint_number)).all()
        output.append(HistoryDriver(
            driver_id=driver.id,
            name=entry.abbreviation or driver.abbreviation or driver.full_name,
            team=constructor.name,
            team_image_id=logo_id,
            driver_color=color,
            laps=[HistoryLap(lap_number=l.lap_number, position=l.position, laptime=_duration(l.lap_time_us), gaptime=_gap_seconds(l.gap_to_leader_us)) for l in laps],
            tire=[TireStintResponse(tire_type=s.compound, startlap=s.start_lap, endlap=s.end_lap) for s in stints],
        ))
    return GrandPrixHistoryResponse(flags=flags, driver=output)


def _is_completed_status(status_text: str | None) -> bool:
    if not status_text:
        return False
    text = status_text.strip().lower()
    return text == "finished" or text.startswith("+") or "lap" in text


def get_grand_prix_detail(db: Session, grand_prix_id: int, session_type: SessionType) -> list[GrandPrixDetailDriver]:
    gp = _get_gp(db, grand_prix_id)
    session_row = _get_session(db, gp.id, session_type)
    rows = db.execute(
        select(SessionEntry, SessionResult, Driver, Constructor)
        .join(SessionResult, SessionResult.session_entry_id == SessionEntry.id)
        .join(Driver, Driver.id == SessionEntry.driver_id)
        .join(Constructor, Constructor.id == SessionEntry.constructor_id)
        .where(SessionEntry.session_id == session_row.id)
        .order_by(SessionResult.finishing_position, SessionEntry.id)
    ).all()

    result_list: list[GrandPrixDetailDriver] = []
    for entry, result, driver, constructor in rows:
        logo_id, color = _team_meta(db, gp.season_year, constructor.id)
        stints = db.scalars(select(TyreStint).where(TyreStint.session_entry_id == entry.id).order_by(TyreStint.stint_number)).all()
        s1, s2, s3, speedtrap = db.execute(
            select(
                func.min(Lap.sector1_time_us),
                func.min(Lap.sector2_time_us),
                func.min(Lap.sector3_time_us),
                func.max(Lap.speed_st_kph),
            ).where(Lap.session_entry_id == entry.id)
        ).one()
        theoretical = s1 + s2 + s3 if None not in (s1, s2, s3) else None
        race_or_sprint = session_type in {SessionType.R, SessionType.S}
        result_list.append(GrandPrixDetailDriver(
            driver_id=driver.id,
            name=driver.full_name,
            team_image_id=logo_id,
            team_color=color,
            racetime=_duration(result.total_time_us),
            fastestlap=_duration(result.fastest_lap_time),
            speedtrap=_float(speedtrap),
            is_completed=_is_completed_status(result.status),
            tire=[TireStintResponse(tire_type=s.compound, startlap=s.start_lap, endlap=s.end_lap) for s in stints],
            theoretical_lap_time=None if race_or_sprint else _duration(theoretical),
            sector1_time=None if race_or_sprint else _duration(s1),
            sector2_time=None if race_or_sprint else _duration(s2),
            sector3_time=None if race_or_sprint else _duration(s3),
            lap_amount=result.laps_completed if race_or_sprint else None,
            points=_float(result.points) if race_or_sprint else None,
        ))
    return result_list


def get_driver_championship(db: Session, season: int | None, after_round: int | None) -> list[ChampionshipDriverItem]:
    season = resolve_season(db, season)
    after_round = after_round or _latest_round(db, season, DriverStanding)
    changes = _driver_rank_changes(db, season, after_round)
    rows = db.execute(
        select(DriverStanding, Driver, Constructor)
        .join(Driver, Driver.id == DriverStanding.driver_id)
        .outerjoin(Constructor, Constructor.id == DriverStanding.constructor_id)
        .where(DriverStanding.season_year == season, DriverStanding.after_round == after_round)
        .order_by(DriverStanding.position)
    ).all()
    output: list[ChampionshipDriverItem] = []
    for standing, driver, constructor in rows:
        logo_id = None
        if constructor:
            logo_id, _ = _team_meta(db, season, constructor.id)
        output.append(ChampionshipDriverItem(
            driver_id=driver.id,
            name=driver.full_name,
            teamname=constructor.name if constructor else "",
            team_image_id=logo_id,
            points=float(standing.points),
            rank_change=changes.get(driver.id, 0),
        ))
    return output


def get_constructor_championship(db: Session, season: int | None, after_round: int | None) -> list[ChampionshipConstructorItem]:
    season = resolve_season(db, season)
    after_round = after_round or _latest_round(db, season, ConstructorStanding)
    changes = _constructor_rank_changes(db, season, after_round)
    rows = db.execute(
        select(ConstructorStanding, Constructor)
        .join(Constructor, Constructor.id == ConstructorStanding.constructor_id)
        .where(ConstructorStanding.season_year == season, ConstructorStanding.after_round == after_round)
        .order_by(ConstructorStanding.position)
    ).all()
    output: list[ChampionshipConstructorItem] = []
    for standing, constructor in rows:
        logo_id, _ = _team_meta(db, season, constructor.id)
        output.append(ChampionshipConstructorItem(
            team_id=constructor.id,
            team_name=constructor.name,
            team_image_id=logo_id,
            points=float(standing.points),
            rank_change=changes.get(constructor.id, 0),
        ))
    return output


def get_circuit(db: Session, circuit_id: int) -> CircuitResponse:
    circuit = db.get(Circuit, circuit_id)
    if circuit is None:
        raise _not_found("Circuit not found")
    layout = db.scalar(
        select(CircuitLayout)
        .where(CircuitLayout.circuit_id == circuit.id)
        .order_by(CircuitLayout.is_current.desc(), CircuitLayout.valid_from_year.desc())
        .limit(1)
    )

    record_items: list[CircuitRecordItem] = []
    if layout:
        rows = db.execute(
            select(CircuitRecord, Driver, Constructor)
            .outerjoin(Driver, Driver.id == CircuitRecord.driver_id)
            .outerjoin(Constructor, Constructor.id == CircuitRecord.constructor_id)
            .where(CircuitRecord.circuit_layout_id == layout.id)
            .order_by(CircuitRecord.record_type)
        ).all()
        for record, driver, constructor in rows:
            public_type = {"RACE_LAP": "LAP", "TRACK_LAP": "TRACK"}.get(record.record_type, record.record_type)
            record_items.append(CircuitRecordItem(
                record_type=public_type,
                driver_id=driver.id if driver else None,
                driver_name=driver.full_name if driver else None,
                record_year=record.record_year,
                driver_team=constructor.name if constructor else None,
                record_time=_duration(record.lap_time_us),
            ))

    # LASTWIN is derived, not duplicated in circuit_records.
    last_win = db.execute(
        select(GrandPrix, Driver, Constructor)
        .join(Driver, Driver.id == GrandPrix.winning_driver_id)
        .outerjoin(Constructor, Constructor.id == GrandPrix.winning_constructor_id)
        .where(GrandPrix.circuit_id == circuit.id, GrandPrix.winning_driver_id.is_not(None))
        .order_by(GrandPrix.season_year.desc(), GrandPrix.round_number.desc())
        .limit(1)
    ).first()
    if last_win:
        gp, driver, constructor = last_win
        record_items.append(CircuitRecordItem(
            record_type="LASTWIN",
            driver_id=driver.id,
            driver_name=driver.full_name,
            record_year=gp.season_year,
            driver_team=constructor.name if constructor else None,
            record_time=None,
        ))

    length_m = layout.length_meters if layout and layout.length_meters else circuit.length_meters
    return CircuitResponse(
        circuit_korean_name=circuit.name_ko,
        circuit_english_name=circuit.name,
        circuit_image_id=layout.map_image_id if layout else None,
        circuit_one_lap_length=(length_m / 1000 if length_m else None),
        circuit_corners=layout.corners if layout else None,
        circuit_opening_year=circuit.opening_year,
        record=record_items,
    )
