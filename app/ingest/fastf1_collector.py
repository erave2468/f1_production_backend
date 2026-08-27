
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Circuit,
    Constructor,
    ConstructorStanding,
    Country,
    Driver,
    DriverStanding,
    GrandPrix,
    Lap,
    PitStop,
    RaceControlEvent,
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
from app.ingest.helpers import (
    clean_bool,
    clean_date,
    clean_decimal,
    clean_int,
    clean_str,
    first_present,
    is_missing,
    list_last,
    session_time_to_datetime,
    slugify,
    td_to_us,
    to_utc_naive,
)
from app.country_data import (
    country_code_from_text,
    seed_countries,
)
log = logging.getLogger(__name__)

def _source_str(
    value: Any,
    *,
    max_len: int | None = None,
) -> str | None:
    if is_missing(value):
        return None

    value = clean_str(
        value,
        max_len=max_len,
    )

    if not value:
        return None

    if value.strip().lower() in {
        "none",
        "nan",
        "nat",
        "<na>",
        "null",
    }:
        return None

    return value

SESSION_NAME_TO_TYPE: dict[str, SessionType] = {
    "practice 1": SessionType.FP1,
    "fp1": SessionType.FP1,
    "practice 2": SessionType.FP2,
    "fp2": SessionType.FP2,
    "practice 3": SessionType.FP3,
    "fp3": SessionType.FP3,
    "qualifying": SessionType.Q,
    "q": SessionType.Q,
    "sprint shootout": SessionType.SQ,
    "sprint qualifying": SessionType.SQ,
    "sq": SessionType.SQ,
    "sprint": SessionType.S,
    "s": SessionType.S,
    "race": SessionType.R,
    "r": SessionType.R,
}


def _fastf1_modules():
    try:
        import fastf1
        from fastf1.ergast import Ergast
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "FastF1 is not installed. Run: pip install -r requirements.txt"
        ) from exc
    return fastf1, Ergast


def configure_fastf1_cache() -> None:
    fastf1, _ = _fastf1_modules()
    cache_dir = Path(settings.fastf1_cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))


def _upsert_by(session: Session, model: type, filters: dict[str, Any], values: dict[str, Any]):
    obj = session.scalar(select(model).filter_by(**filters))
    if obj is None:
        obj = model(**filters, **values)
        session.add(obj)
        session.flush()
    else:
        for key, value in values.items():
            if value is not None:
                setattr(obj, key, value)
        session.flush()
    return obj


def _ensure_season(db: Session, year: int, schedule: pd.DataFrame | None = None) -> Season:
    values: dict[str, Any] = {}
    if schedule is not None and not schedule.empty:
        races = schedule.copy()
        if "RoundNumber" in races.columns:
            real_races = races[pd.to_numeric(races["RoundNumber"], errors="coerce").fillna(0) > 0]
        else:
            real_races = races
        values["total_rounds"] = len(real_races)
        if "EventDate" in real_races.columns:
            dates = pd.to_datetime(real_races["EventDate"], errors="coerce", utc=True).dropna()
            if not dates.empty:
                values["start_date"] = dates.min().date()
                values["end_date"] = dates.max().date()
    return _upsert_by(db, Season, {"year": year}, values)


def _ensure_driver_from_row(
    db: Session,
    row: Any,
) -> Driver:
    ref = _source_str(first_present(row,"DriverId","driverId","driver_ref",))
    full_name = _source_str(first_present(row,"FullName","fullName",))
    given = _source_str(first_present(row,"givenName","FirstName",))
    family = _source_str(first_present(row,"familyName","LastName",))
    abbreviation = _source_str(first_present(row,"Abbreviation","driverCode","code",),max_len=3,)

    if abbreviation:
        abbreviation = abbreviation.upper()

    number = clean_int(first_present(row,"DriverNumber","permanentNumber","driverNumber",),positive_only=True,)
    nationality = _source_str(first_present(row,"driverNationality","nationality",))
    date_of_birth = clean_date(first_present(row,"dateOfBirth","DateOfBirth",))

    if not full_name:
        name_parts = [
            part
            for part in (
                given,
                family,
            )
            if part
        ]

        if name_parts:
            full_name = " ".join(
                name_parts
            )
        else:
            full_name = _source_str(
                first_present(
                    row,
                    "BroadcastName",
                    "Driver",
                )
            )

    driver = None

    if ref:
        candidate = db.scalar(
            select(Driver)
            .where(
                Driver.driver_ref == ref
            )
        )

        if candidate is not None:
            # upstream ref가 기존 Driver를 가리키더라도
            # abbreviation이 명백히 다르면
            # 잘못된 매칭으로 간주
            if (
                abbreviation
                and candidate.abbreviation
                and candidate.abbreviation.upper()
                != abbreviation.upper()
            ):
                log.warning(
                    "Driver ref conflict: "
                    "ref=%s resolved to id=%s "
                    "abbr=%s, incoming abbr=%s; "
                    "ignoring ref match",
                    ref,
                    candidate.id,
                    candidate.abbreviation,
                    abbreviation,
                )
            else:
                driver = candidate

    if driver is None and abbreviation:
        candidates = db.scalars(
            select(Driver)
            .where(
                func.upper(Driver.abbreviation)
                == abbreviation.upper()
            )
        ).all()

        if len(candidates) == 1:
            driver = candidates[0]

        elif len(candidates) > 1:
            # 생년월일 우선
            if date_of_birth:
                matches = [
                    candidate
                    for candidate in candidates
                    if candidate.date_of_birth
                    == date_of_birth
                ]

                if len(matches) == 1:
                    driver = matches[0]

            # 그래도 못 찾으면 번호 보조
            if driver is None and number:
                matches = [
                    candidate
                    for candidate in candidates
                    if candidate.permanent_number
                    == number
                ]

                if len(matches) == 1:
                    driver = matches[0]

            if driver is None:
                raise RuntimeError(
                    "Ambiguous driver abbreviation "
                    f"{abbreviation}: "
                    f"{[(d.id, d.driver_ref, d.full_name) for d in candidates]}"
                )


    if driver is not None:
        if abbreviation:
            driver.abbreviation = abbreviation

        if number:
            driver.permanent_number = number

        if full_name:
            driver.full_name = full_name

        if nationality:
            driver.nationality = nationality

            driver.nationality_code = (
                country_code_from_text(
                    nationality
                )
            )

        if date_of_birth:
            driver.date_of_birth = date_of_birth

        db.flush()

        return driver

    if not ref:
        if full_name:
            ref = slugify(
                full_name,
                f"driver_{number or 'unknown'}",
            )

        elif abbreviation:
            ref = (
                f"driver_{abbreviation.lower()}"
            )

        elif number:
            ref = f"driver_{number}"

        else:
            raise RuntimeError(
                "Cannot identify driver: "
                "no ref, abbreviation, "
                "name or number"
            )

    driver = Driver(
        driver_ref=ref,
        permanent_number=number,
        abbreviation=abbreviation,
        full_name=(
            full_name
            or abbreviation
            or ref
        ),
        nationality=nationality,
        nationality_code=(
            country_code_from_text(
                nationality
            )
            if nationality
            else None
        ),
        date_of_birth=date_of_birth,
    )

    db.add(driver)
    db.flush()

    return driver


def _ensure_constructor_from_row(db: Session, row: Any) -> Constructor:
    ref = clean_str(first_present(row, "TeamId", "constructorId", "constructor_ref"))
    name = clean_str(first_present(row, "TeamName", "constructorName", "name", "Constructor"))
    nationality = clean_str(first_present(row,"constructorNationality","nationality",))
    if not ref:
        ref = slugify(name, "constructor_unknown")
    return _upsert_by(
        db,
        Constructor,
        {"constructor_ref": ref},
        {
            "name": name or ref,
            "full_name": clean_str(
                first_present(
                    row,
                    "FullTeamName",
                    "constructorFullName",
                )
            ),
            "nationality": nationality,
            "nationality_code": country_code_from_text(
                nationality
            ),
        },
    )


def _ensure_circuit_from_row(db: Session, row: Any) -> Circuit:
    ref = clean_str(first_present(row, "circuitId", "CircuitId"))
    name = clean_str(first_present(row, "circuitName", "CircuitName", "Location"))
    country_name = clean_str(first_present(row,"country","Country",))
    if not ref:
        ref = slugify(name, "circuit_unknown")
    return _upsert_by(
        db,
        Circuit,
        {"circuit_ref": ref},
        {
            "name": name or ref,
            "city": clean_str(
                first_present(
                    row,
                    "locality",
                    "Locality",
                )
            ),
            "country": country_name,
            "country_code": country_code_from_text(
                country_name
            ),
            "latitude": clean_decimal(
                first_present(
                    row,
                    "lat",
                    "Latitude",
                )
            ),
            "longitude": clean_decimal(
                first_present(
                    row,
                    "long",
                    "Longitude",
                )
            ),
        },
    )


def ingest_reference_data(db: Session, year: int) -> None:
    """Populate season, drivers, constructors and circuits from FastF1's Ergast/Jolpica interface."""
    _, Ergast = _fastf1_modules()

    
    ergast = Ergast(result_type="pandas", auto_cast=True, limit=1000)

    drivers = ergast.get_driver_info(season=year)
    constructors = ergast.get_constructor_info(season=year)
    circuits = ergast.get_circuits(season=year)

    seed_countries(db)

    _ensure_season(db, year)
    for _, row in drivers.iterrows():
        _ensure_driver_from_row(db, row)
    for _, row in constructors.iterrows():
        _ensure_constructor_from_row(db, row)
    for _, row in circuits.iterrows():
        _ensure_circuit_from_row(db, row)
    db.commit()


def _event_session_slots(row: Any) -> Iterable[tuple[str, Any]]:
    for i in range(1, 6):
        name = clean_str(first_present(row, f"Session{i}"))
        if not name:
            continue
        # UTC column is preferred because MySQL storage is normalized to UTC.
        dt = first_present(row, f"Session{i}DateUtc", f"Session{i}Date")
        yield name, dt


def normalize_session_type(name: str) -> SessionType | None:
    key = name.strip().lower()
    return SESSION_NAME_TO_TYPE.get(key)


def ingest_schedule(db: Session, year: int) -> None:
    """Create GrandPrix and Session rows from FastF1's event schedule."""
    fastf1, Ergast = _fastf1_modules()
    ff_schedule = fastf1.get_event_schedule(year, include_testing=False)
    seed_countries(db)
    _ensure_season(db, year, ff_schedule)

    # Ergast schedule gives stable circuit identifiers/locations.
    ergast = Ergast(result_type="pandas", auto_cast=True, limit=1000)
    erg_schedule = ergast.get_race_schedule(season=year)
    erg_by_round: dict[int, Any] = {}
    if erg_schedule is not None:
        for _, r in erg_schedule.iterrows():
            rnd = clean_int(first_present(r, "round", "RoundNumber"), positive_only=True)
            if rnd:
                erg_by_round[rnd] = r

    for _, row in ff_schedule.iterrows():
        round_number = clean_int(first_present(row, "RoundNumber"), positive_only=True)
        if not round_number:
            continue

        erg_row = erg_by_round.get(round_number)
        if erg_row is not None:
            circuit = _ensure_circuit_from_row(db, erg_row)
        else:
            # Fallback if Jolpica is temporarily unavailable/incomplete.
            circuit = _ensure_circuit_from_row(db, row)

        session_dates = [to_utc_naive(dt) for _, dt in _event_session_slots(row)]
        session_dates = [dt for dt in session_dates if dt]
        event_date = to_utc_naive(first_present(row, "EventDate"))
        start_date = min(session_dates).date() if session_dates else (event_date.date() if event_date else None)
        end_date = max(session_dates).date() if session_dates else (event_date.date() if event_date else None)

        event_country = clean_str(
            first_present(
                row,
                "Country",
                "country",
            )
        )

        event_country_code = (
            country_code_from_text(event_country)
            or circuit.country_code
        )

        gp = _upsert_by(
            db,
            GrandPrix,
            {"season_year": year, "round_number": round_number},
            {
                "circuit_id": circuit.id,
                "official_name": clean_str(first_present(row, "OfficialEventName")),
                "display_name": clean_str(first_present(row, "EventName")) or f"Round {round_number}",
                "event_format": clean_str(first_present(row, "EventFormat")),
                "weekend_start_date": start_date,
                "weekend_end_date": end_date,
                "status": "scheduled",
                "country_code": event_country_code,
            },
        )

        slots = list(_event_session_slots(row))
        for idx, (session_name, session_dt) in enumerate(slots):
            session_type = normalize_session_type(session_name)
            if not session_type:
                log.warning("Unknown FastF1 session name %r, skipping", session_name)
                continue
            scheduled_start = to_utc_naive(session_dt)
            scheduled_end = None
            if idx + 1 < len(slots):
                next_start = to_utc_naive(slots[idx + 1][1])
                # The next session is not the true end, but can provide an upper bound.
                # We intentionally leave scheduled_end NULL rather than inventing a duration.
                _ = next_start
            _upsert_by(
                db,
                SessionModel,
                {"grand_prix_id": gp.id, "type": session_type},
                {
                    "name": session_name,
                    "scheduled_start": scheduled_start,
                    "scheduled_end": scheduled_end,
                    "status": "scheduled",
                },
            )

    db.commit()


def _update_season_entries(
    db: Session,
    *,
    year: int,
    round_number: int,
    driver: Driver,
    constructor: Constructor,
    result_row: Any,
    session_type: SessionType,
) -> None:
    team_color = clean_str(first_present(result_row, "TeamColor"))
    if team_color and not team_color.startswith("#"):
        team_color = f"#{team_color}"
    existing = db.scalar(
        select(SeasonDriverEntry).filter_by(
            season_year=year,
            driver_id=driver.id,
            constructor_id=constructor.id,
        )
    )
    if existing is None:
        existing = SeasonDriverEntry(
            season_year=year,
            driver_id=driver.id,
            constructor_id=constructor.id,
            color=team_color,
            car_number=clean_int(first_present(result_row, "DriverNumber"), positive_only=True),
            start_round=round_number,
            end_round=round_number,
            is_primary_driver=(True if session_type in {SessionType.R, SessionType.S} else None),
        )
        db.add(existing)
    else:
        existing.start_round = min(existing.start_round or round_number, round_number)
        existing.end_round = max(existing.end_round or round_number, round_number)
        if team_color:
            existing.color = team_color
        number = clean_int(first_present(result_row, "DriverNumber"), positive_only=True)
        if number:
            existing.car_number = number
        if session_type in {SessionType.R, SessionType.S}:
            existing.is_primary_driver = True

    _upsert_by(
        db,
        SeasonConstructorEntry,
        {"season_year": year, "constructor_id": constructor.id},
        {
            "entry_name": constructor.name,
            "color": team_color,
        },
    )


def _clear_session_payload(db: Session, session_row: SessionModel) -> None:
    """Delete mutable payload so reruns reproduce the latest official data cleanly."""
    # race_periods references race_control_events, so delete it first.
    db.execute(delete(RacePeriod).where(RacePeriod.session_id == session_row.id))
    db.execute(delete(RaceControlEvent).where(RaceControlEvent.session_id == session_row.id))
    db.execute(delete(WeatherSample).where(WeatherSample.session_id == session_row.id))
    # Cascades clear results/laps/stints/pits beneath entries.
    db.execute(delete(SessionEntry).where(SessionEntry.session_id == session_row.id))
    db.flush()


def _find_fastest_lap(laps: pd.DataFrame, driver_number: str | None) -> tuple[int | None, int | None]:
    if laps is None or laps.empty or not driver_number:
        return None, None
    subset = laps[laps["DriverNumber"].astype(str) == str(driver_number)] if "DriverNumber" in laps.columns else pd.DataFrame()
    if subset.empty or "LapTime" not in subset.columns:
        return None, None
    timed = subset[subset["LapTime"].notna()]
    if timed.empty:
        return None, None
    idx = timed["LapTime"].idxmin()
    row = timed.loc[idx]
    return clean_int(first_present(row, "LapNumber"), positive_only=True), td_to_us(first_present(row, "LapTime"))


def _derive_actual_times(ff_session: Any) -> tuple[Any, Any]:
    start = None
    end = None
    try:
        start = session_time_to_datetime(ff_session, ff_session.session_start_time)
    except (AttributeError, ValueError):
        pass
    try:
        status = ff_session.session_status
        if status is not None and not status.empty and "Time" in status.columns:
            end = session_time_to_datetime(ff_session, status.iloc[-1]["Time"])
    except (AttributeError, KeyError, IndexError):
        pass
    if end is None:
        try:
            laps = ff_session.laps
            if laps is not None and not laps.empty and "Time" in laps.columns:
                value = laps["Time"].dropna().max()
                end = session_time_to_datetime(ff_session, value)
        except (AttributeError, KeyError, ValueError):
            pass
    return start, end

def _ingest_results_and_entries(
    db: Session,
    ff_session: Any,
    session_row: SessionModel,
    gp: GrandPrix,
) -> dict[str, SessionEntry]:
    results = ff_session.results
    laps = ff_session.laps

    entries_by_number: dict[
        str,
        SessionEntry,
    ] = {}

    # 동일 세션에서 같은 driver_id가
    # 두 번 매칭되는 문제를 미리 감지
    seen_driver_ids: dict[
        int,
        dict[str, str | None],
    ] = {}

    # Practice/recent sessions can occasionally
    # have no external result table yet.
    if results is None or results.empty:
        fallback_rows = []

        for number in (
            getattr(
                ff_session,
                "drivers",
                [],
            )
            or []
        ):
            try:
                fallback_rows.append(
                    ff_session.get_driver(
                        str(number)
                    )
                )

            except Exception:
                log.warning(
                    "Could not build driver row "
                    "for number %s",
                    number,
                )

        results = pd.DataFrame(
            fallback_rows
        )

    # ─────────────────────────────
    # Winner time
    # ─────────────────────────────

    winner_time_us: int | None = None

    if not results.empty:
        for _, row in results.iterrows():
            position = clean_int(
                first_present(
                    row,
                    "Position",
                ),
                positive_only=True,
            )

            if position == 1:
                winner_time_us = td_to_us(
                    first_present(
                        row,
                        "Time",
                    )
                )
                break

    # ─────────────────────────────
    # Driver entries/results
    # ─────────────────────────────

    for _, row in results.iterrows():
        driver = _ensure_driver_from_row(
            db,
            row,
        )

        constructor = (
            _ensure_constructor_from_row(
                db,
                row,
            )
        )

        number = clean_str(
            first_present(
                row,
                "DriverNumber",
            )
        )

        abbreviation = clean_str(
            first_present(
                row,
                "Abbreviation",
                "driverCode",
                "code",
            ),
            max_len=3,
        )

        if abbreviation:
            abbreviation = (
                abbreviation.upper()
            )

        source_ref = clean_str(
            first_present(
                row,
                "DriverId",
                "driverId",
                "driver_ref",
            )
        )

        source_name = clean_str(
            first_present(
                row,
                "FullName",
                "fullName",
                "BroadcastName",
                "Driver",
            )
        )

        # ─────────────────────────
        # Driver resolver collision check
        # ─────────────────────────

        if driver.id in seen_driver_ids:
            previous = (
                seen_driver_ids[
                    driver.id
                ]
            )

            raise RuntimeError(
                "Driver resolver collision "
                f"in session {session_row.id}: "
                f"driver_id={driver.id}; "
                f"previous={previous}; "
                f"current={{"
                f"'number': {number!r}, "
                f"'abbreviation': "
                f"{abbreviation!r}, "
                f"'ref': {source_ref!r}, "
                f"'name': {source_name!r}"
                f"}}"
            )

        seen_driver_ids[
            driver.id
        ] = {
            "number": number,
            "abbreviation": abbreviation,
            "ref": source_ref,
            "name": source_name,
        }

        grid = clean_int(
            first_present(
                row,
                "GridPosition",
            ),
            positive_only=True,
        )

        entry = SessionEntry(
            session_id=session_row.id,
            driver_id=driver.id,
            constructor_id=constructor.id,
            racing_number=clean_int(
                number,
                positive_only=True,
            ),
            abbreviation=abbreviation,
            grid_position=grid,
        )

        db.add(entry)
        db.flush()

        if number:
            entries_by_number[
                str(number)
            ] = entry

        # ─────────────────────────
        # Result
        # ─────────────────────────

        finishing_position = clean_int(
            first_present(
                row,
                "Position",
            ),
            positive_only=True,
        )

        classified_raw = clean_str(
            first_present(
                row,
                "ClassifiedPosition",
            )
        )

        classified_position = clean_int(
            classified_raw,
            positive_only=True,
        )

        displayed_position = (
            classified_raw
            or (
                str(finishing_position)
                if finishing_position
                else None
            )
        )

        total_time_us = td_to_us(
            first_present(
                row,
                "Time",
            )
        )

        gap = None

        if (
            total_time_us is not None
            and winner_time_us is not None
        ):
            gap = max(
                0,
                total_time_us
                - winner_time_us,
            )

        (
            fastest_lap_number,
            fastest_lap_time,
        ) = _find_fastest_lap(
            laps,
            number,
        )

        db.add(
            SessionResult(
                session_entry_id=entry.id,

                classified_position=(
                    classified_position
                ),

                displayed_position=(
                    displayed_position
                ),

                grid_position=grid,

                finishing_position=(
                    finishing_position
                ),

                points=clean_decimal(
                    first_present(
                        row,
                        "Points",
                    )
                ),

                status=clean_str(
                    first_present(
                        row,
                        "Status",
                    )
                ),

                laps_completed=clean_int(
                    first_present(
                        row,
                        "Laps",
                    )
                ),

                total_time_us=total_time_us,

                gap_to_winner_us=gap,

                fastest_lap_number=(
                    fastest_lap_number
                ),

                fastest_lap_time=(
                    fastest_lap_time
                ),

                q1_time_us=td_to_us(
                    first_present(
                        row,
                        "Q1",
                    )
                ),

                q2_time_us=td_to_us(
                    first_present(
                        row,
                        "Q2",
                    )
                ),

                q3_time_us=td_to_us(
                    first_present(
                        row,
                        "Q3",
                    )
                ),
            )
        )

        _update_season_entries(
            db,
            year=gp.season_year,
            round_number=(
                gp.round_number
            ),
            driver=driver,
            constructor=constructor,
            result_row=row,
            session_type=(
                session_row.type
            ),
        )

        if (
            session_row.type
            == SessionType.R
            and finishing_position == 1
        ):
            gp.winning_driver_id = (
                driver.id
            )

            gp.winning_constructor_id = (
                constructor.id
            )

            gp.status = "completed"

    return entries_by_number


def _ingest_laps(db: Session, ff_session: Any, entries: dict[str, SessionEntry]) -> None:
    laps = ff_session.laps
    if laps is None or laps.empty:
        return
    for _, row in laps.iterrows():
        number = clean_str(first_present(row, "DriverNumber"))
        entry = entries.get(str(number)) if number else None
        lap_no = clean_int(first_present(row, "LapNumber"), positive_only=True)
        if entry is None or lap_no is None:
            continue
        db.add(
            Lap(
                session_entry_id=entry.id,
                lap_number=lap_no,
                position=clean_int(first_present(row, "Position"), positive_only=True),
                lap_time_us=td_to_us(first_present(row, "LapTime")),
                sector1_time_us=td_to_us(first_present(row, "Sector1Time")),
                sector2_time_us=td_to_us(first_present(row, "Sector2Time")),
                sector3_time_us=td_to_us(first_present(row, "Sector3Time")),
                # Standard FastF1 Laps has no official per-lap gap/interval columns.
                gap_to_leader_us=None,
                interval_to_ahead_us=None,
                compound=clean_str(first_present(row, "Compound"), max_len=24),
                tyre_life_laps=clean_int(first_present(row, "TyreLife")),
                stint_number=clean_int(first_present(row, "Stint"), positive_only=True),
                pit_in_time_us=td_to_us(first_present(row, "PitInTime")),
                pit_out_time_us=td_to_us(first_present(row, "PitOutTime")),
                track_status=clean_str(first_present(row, "TrackStatus"), max_len=32),
                speed_i1_kph=clean_decimal(first_present(row, "SpeedI1")),
                speed_i2_kph=clean_decimal(first_present(row, "SpeedI2")),
                speed_fl_kph=clean_decimal(first_present(row, "SpeedFL")),
                speed_st_kph=clean_decimal(first_present(row, "SpeedST")),
            )
        )


def _ingest_stints(db: Session, ff_session: Any, entries: dict[str, SessionEntry]) -> None:
    laps = ff_session.laps
    if laps is None or laps.empty or "Stint" not in laps.columns:
        return
    work = laps[laps["Stint"].notna() & laps["LapNumber"].notna()].copy()
    if work.empty:
        return
    for (driver_number, stint_raw), group in work.groupby(["DriverNumber", "Stint"], dropna=True):
        entry = entries.get(str(driver_number))
        stint = clean_int(stint_raw, positive_only=True)
        if entry is None or stint is None:
            continue
        group = group.sort_values("LapNumber")
        first = group.iloc[0]
        last = group.iloc[-1]
        compound_series = group["Compound"].dropna() if "Compound" in group.columns else pd.Series(dtype=object)
        compound = clean_str(compound_series.iloc[0]) if not compound_series.empty else None
        fresh_series = group["FreshTyre"].dropna() if "FreshTyre" in group.columns else pd.Series(dtype=object)
        db.add(
            TyreStint(
                session_entry_id=entry.id,
                stint_number=stint,
                compound=compound,
                start_lap=clean_int(first_present(first, "LapNumber"), positive_only=True) or 1,
                end_lap=clean_int(first_present(last, "LapNumber"), positive_only=True) or 1,
                starting_tyre_life=clean_int(first_present(first, "TyreLife")),
                ending_tyre_life=clean_int(first_present(last, "TyreLife")),
                fresh_tyre=(clean_bool(fresh_series.iloc[0]) if not fresh_series.empty else None),
            )
        )


def _ingest_pit_stops(db: Session, ff_session: Any, entries: dict[str, SessionEntry]) -> None:
    laps = ff_session.laps
    if laps is None or laps.empty or "PitInTime" not in laps.columns:
        return
    for driver_number, group in laps.groupby("DriverNumber", dropna=True):
        entry = entries.get(str(driver_number))
        if entry is None:
            continue
        group = group.sort_values("LapNumber").reset_index(drop=True)
        stop_number = 0
        for idx, row in group.iterrows():
            pit_in = first_present(row, "PitInTime")
            if is_missing(pit_in):
                continue
            stop_number += 1
            pit_out = None
            compound_after = None
            # PitOutTime is commonly attached to the next lap.
            for j in range(idx, min(idx + 3, len(group))):
                candidate = first_present(group.iloc[j], "PitOutTime")
                if not is_missing(candidate):
                    pit_out = candidate
                    compound_after = clean_str(first_present(group.iloc[j], "Compound"))
                    break
            pit_in_us = td_to_us(pit_in)
            pit_out_us = td_to_us(pit_out)
            lane_duration = (
                pit_out_us - pit_in_us
                if pit_in_us is not None and pit_out_us is not None and pit_out_us >= pit_in_us
                else None
            )
            db.add(
                PitStop(
                    session_entry_id=entry.id,
                    stop_number=stop_number,
                    lap_number=clean_int(first_present(row, "LapNumber"), positive_only=True),
                    pit_entry_time_us=pit_in_us,
                    pit_exit_time_us=pit_out_us,
                    pit_lane_duration_us=lane_duration,
                    # Stationary time is not contained in the normal FastF1 Laps table.
                    stationary_duration_us=None,
                    compound_before=clean_str(first_present(row, "Compound")),
                    compound_after=compound_after,
                )
            )


def _ingest_weather(db: Session, ff_session: Any, session_row: SessionModel) -> None:
    weather = ff_session.weather_data
    if weather is None or weather.empty:
        return
    for _, row in weather.iterrows():
        time_value = first_present(row, "Time")
        time_us = td_to_us(time_value)
        if time_us is None:
            continue
        db.add(
            WeatherSample(
                session_id=session_row.id,
                sample_time=session_time_to_datetime(ff_session, time_value),
                session_time_us=time_us,
                air_temperature_c=clean_decimal(first_present(row, "AirTemp")),
                track_temperature_c=clean_decimal(first_present(row, "TrackTemp")),
                humidity_percent=clean_decimal(first_present(row, "Humidity")),
                pressure_hpa=clean_decimal(first_present(row, "Pressure")),
                wind_speed_mps=clean_decimal(first_present(row, "WindSpeed")),
                wind_direction_deg=clean_int(first_present(row, "WindDirection")),
                rainfall=clean_bool(first_present(row, "Rainfall")),
            )
        )


def _ingest_race_control(db: Session, ff_session: Any, session_row: SessionModel) -> None:
    messages = ff_session.race_control_messages
    if messages is None or messages.empty:
        return
    for _, row in messages.iterrows():
        time_value = first_present(row, "Time")
        message = clean_str(first_present(row, "Message")) or ""
        db.add(
            RaceControlEvent(
                session_id=session_row.id,
                lap_number=clean_int(first_present(row, "Lap"), positive_only=True),
                event_time=session_time_to_datetime(ff_session, time_value),
                session_time_us=td_to_us(time_value),
                category=clean_str(first_present(row, "Category"), max_len=80),
                event_type=clean_str(first_present(row, "Mode", "Type", "Scope"), max_len=80),
                flag=clean_str(first_present(row, "Flag"), max_len=40),
                status=clean_str(first_present(row, "Status"), max_len=80),
                message=message,
            )
        )


def ingest_session(db: Session, year: int, round_number: int, session_code: str) -> None:
    """Download one FastF1 session and replace its mutable DB payload atomically."""
    fastf1, _ = _fastf1_modules()
    session_type = normalize_session_type(session_code)
    if session_type is None:
        raise ValueError(f"Unsupported session code/name: {session_code}")

    gp = db.scalar(select(GrandPrix).filter_by(season_year=year, round_number=round_number))
    if gp is None:
        ingest_schedule(db, year)
        gp = db.scalar(select(GrandPrix).filter_by(season_year=year, round_number=round_number))
    if gp is None:
        raise LookupError(f"No Grand Prix found for {year} round {round_number}")

    session_row = db.scalar(select(SessionModel).filter_by(grand_prix_id=gp.id, type=session_type))
    if session_row is None:
        session_row = SessionModel(
            grand_prix_id=gp.id,
            type=session_type,
            name=session_code,
            status="scheduled",
        )
        db.add(session_row)
        db.flush()

    log.info("Loading FastF1: %s round %s %s", year, round_number, session_type.value)
    ff_session = fastf1.get_session(year, round_number, session_type.value)
    # ERD stores laps/results/weather/messages, not raw car telemetry.
    ff_session.load(laps=True, telemetry=True, weather=True, messages=True)

    _clear_session_payload(db, session_row)
    entries = _ingest_results_and_entries(db, ff_session, session_row, gp)
    _ingest_laps(db, ff_session, entries)
    _ingest_stints(db, ff_session, entries)
    _ingest_pit_stops(db, ff_session, entries)
    _ingest_weather(db, ff_session, session_row)
    _ingest_race_control(db, ff_session, session_row)
    _ingest_race_periods(db,session_row,)

    actual_start, actual_end = _derive_actual_times(ff_session)
    session_row.actual_start = actual_start
    session_row.actual_end = actual_end
    session_row.total_laps = clean_int(getattr(ff_session, "total_laps", None), positive_only=True)
    session_row.status = "completed"
    db.commit()


def _podium_counts(db: Session, year: int, after_round: int):
    driver_rows = db.execute(
        select(SessionEntry.driver_id, func.count(SessionResult.id))
        .join(SessionResult, SessionResult.session_entry_id == SessionEntry.id)
        .join(SessionModel, SessionModel.id == SessionEntry.session_id)
        .join(GrandPrix, GrandPrix.id == SessionModel.grand_prix_id)
        .where(
            GrandPrix.season_year == year,
            GrandPrix.round_number <= after_round,
            SessionModel.type == SessionType.R,
            SessionResult.finishing_position.between(1, 3),
        )
        .group_by(SessionEntry.driver_id)
    ).all()
    constructor_rows = db.execute(
        select(SessionEntry.constructor_id, func.count(SessionResult.id))
        .join(SessionResult, SessionResult.session_entry_id == SessionEntry.id)
        .join(SessionModel, SessionModel.id == SessionEntry.session_id)
        .join(GrandPrix, GrandPrix.id == SessionModel.grand_prix_id)
        .where(
            GrandPrix.season_year == year,
            GrandPrix.round_number <= after_round,
            SessionModel.type == SessionType.R,
            SessionResult.finishing_position.between(1, 3),
        )
        .group_by(SessionEntry.constructor_id)
    ).all()
    return dict(driver_rows), dict(constructor_rows)


def ingest_standings(db: Session, year: int, after_round: int) -> None:
    _, Ergast = _fastf1_modules()
    ergast = Ergast(result_type="pandas", auto_cast=True, limit=1000)
    drivers_resp = ergast.get_driver_standings(season=year, round=after_round)
    constructors_resp = ergast.get_constructor_standings(season=year, round=after_round)

    driver_df = drivers_resp.content[0] if getattr(drivers_resp, "content", None) else pd.DataFrame()
    constructor_df = constructors_resp.content[0] if getattr(constructors_resp, "content", None) else pd.DataFrame()
    driver_podiums, constructor_podiums = _podium_counts(db, year, after_round)

    for _, row in driver_df.iterrows():
        driver = _ensure_driver_from_row(db, row)
        constructor_id = None
        constructor_ref = clean_str(list_last(first_present(row, "constructorIds", "ConstructorIds")))
        if constructor_ref:
            constructor = db.scalar(select(Constructor).filter_by(constructor_ref=constructor_ref))
            if constructor is None:
                # Standings often include parallel constructorNames/Nationalities lists.
                names = first_present(row, "constructorNames")
                nationalities = first_present(row, "constructorNationalities")
                fake = {
                    "constructorId": constructor_ref,
                    "name": list_last(names),
                    "nationality": list_last(nationalities),
                }
                constructor = _ensure_constructor_from_row(db, fake)
            constructor_id = constructor.id

        _upsert_by(
            db,
            DriverStanding,
            {"season_year": year, "after_round": after_round, "driver_id": driver.id},
            {
                "constructor_id": constructor_id,
                "position": clean_int(first_present(row, "position"), positive_only=True) or 0,
                "points": clean_decimal(first_present(row, "points")) or 0,
                "wins": clean_int(first_present(row, "wins")) or 0,
                "podiums": driver_podiums.get(driver.id, 0),
            },
        )

    for _, row in constructor_df.iterrows():
        constructor = _ensure_constructor_from_row(db, row)
        _upsert_by(
            db,
            ConstructorStanding,
            {"season_year": year, "after_round": after_round, "constructor_id": constructor.id},
            {
                "position": clean_int(first_present(row, "position"), positive_only=True) or 0,
                "points": clean_decimal(first_present(row, "points")) or 0,
                "wins": clean_int(first_present(row, "wins")) or 0,
                "podiums": constructor_podiums.get(constructor.id, 0),
            },
        )
    db.commit()


def ingest_round(db: Session, year: int, round_number: int) -> None:
    """Ingest every scheduled session for a race weekend, then standings."""
    ingest_reference_data(db, year)
    ingest_schedule(db, year)
    gp = db.scalar(select(GrandPrix).filter_by(season_year=year, round_number=round_number))
    if gp is None:
        raise LookupError(f"No Grand Prix found for {year} round {round_number}")
    sessions = db.scalars(
        select(SessionModel)
        .where(SessionModel.grand_prix_id == gp.id)
        .order_by(SessionModel.scheduled_start, SessionModel.id)
    ).all()
    for s in sessions:
        try:
            ingest_session(db, year, round_number, s.type.value)
        except Exception:
            db.rollback()
            log.exception("Failed to ingest %s R%s %s", year, round_number, s.type.value)
            raise
    ingest_standings(db, year, round_number)

def _race_control_text(
    event: RaceControlEvent,
) -> str:
    values = [
        event.category,
        event.event_type,
        event.flag,
        event.status,
        event.message,
    ]

    return " ".join(
        str(value)
        for value in values
        if value
    ).upper()


def _track_event_type(
    event: RaceControlEvent,
) -> str | None:
    text = _race_control_text(event)

    flag = (
        event.flag.upper()
        if event.flag
        else None
    )

    # VSC를 반드시 일반 Safety Car보다
    # 먼저 검사
    if (
        "VIRTUAL SAFETY CAR" in text
        or "VSC" in text
    ):
        return "VSC"

    if "SAFETY CAR" in text:
        return "SAFETY_CAR"

    if (
        flag == "RED"
        or "RED FLAG" in text
    ):
        return "RED_FLAG"

    if (
        flag == "YELLOW"
        or "YELLOW FLAG" in text
    ):
        return "YELLOW_FLAG"

    if (
        flag == "GREEN"
        or "GREEN FLAG" in text
    ):
        return "GREEN_FLAG"

    if (
        flag == "BLUE"
        or "BLUE FLAG" in text
    ):
        return "BLUE_FLAG"

    if (
        "CHEQUERED FLAG" in text
        or "CHECKERED FLAG" in text
    ):
        return "CHEQUERED_FLAG"

    return None

def _ingest_race_periods(
    db: Session,
    session_row: SessionModel,
) -> None:
    # SessionLocal이 autoflush=False이므로
    # 방금 추가한 RaceControlEvent를
    # SELECT 전에 반드시 flush
    db.flush()

    events = db.scalars(
        select(RaceControlEvent)
        .where(
            RaceControlEvent.session_id
            == session_row.id
        )
        .order_by(
            RaceControlEvent.session_time_us,
            RaceControlEvent.id,
        )
    ).all()

    # 현재 진행 중인 구간
    active: dict[
        str,
        RaceControlEvent,
    ] = {}

    def add_period(
        period_type: str,
        start_event: RaceControlEvent,
        end_event: RaceControlEvent | None,
    ) -> None:
        db.add(
            RacePeriod(
                session_id=session_row.id,
                period_type=period_type,

                start_time_us=(
                    start_event.session_time_us
                ),
                end_time_us=(
                    end_event.session_time_us
                    if end_event
                    else None
                ),

                start_lap=(
                    start_event.lap_number
                ),
                end_lap=(
                    end_event.lap_number
                    if end_event
                    else None
                ),

                start_event_id=start_event.id,
                end_event_id=(
                    end_event.id
                    if end_event
                    else None
                ),
            )
        )

    for event in events:
        text = _race_control_text(event)

        event_type = _track_event_type(
            event
        )

        # ───────────────────────
        # RED FLAG 종료
        #
        # Red 이후 GREEN 또는
        # SESSION RESUMED를 만나면 종료
        # ───────────────────────

        if "RED_FLAG" in active:
            red_end = (
                event_type == "GREEN_FLAG"
                or "SESSION RESUM" in text
                or "SESSION RESTART" in text
            )

            if red_end:
                start_event = active.pop(
                    "RED_FLAG"
                )

                add_period(
                    "RED_FLAG",
                    start_event,
                    event,
                )

        # ───────────────────────
        # SAFETY CAR
        # ───────────────────────

        if event_type == "SAFETY_CAR":
            if "DEPLOYED" in text:
                if "SAFETY_CAR" not in active:
                    active[
                        "SAFETY_CAR"
                    ] = event

            elif (
                "IN THIS LAP" in text
                or "ENDING" in text
                or "ENDED" in text
            ):
                start_event = active.pop(
                    "SAFETY_CAR",
                    None,
                )

                if start_event:
                    add_period(
                        "SAFETY_CAR",
                        start_event,
                        event,
                    )

            continue

        # ───────────────────────
        # VIRTUAL SAFETY CAR
        # ───────────────────────

        if event_type == "VSC":
            if "DEPLOYED" in text:
                if "VSC" not in active:
                    active["VSC"] = event

            elif (
                "ENDING" in text
                or "ENDED" in text
            ):
                start_event = active.pop(
                    "VSC",
                    None,
                )

                if start_event:
                    add_period(
                        "VSC",
                        start_event,
                        event,
                    )

            continue

        # ───────────────────────
        # RED FLAG 시작
        # ───────────────────────

        if event_type == "RED_FLAG":
            if "RED_FLAG" not in active:
                active["RED_FLAG"] = event

            continue

        # ───────────────────────
        # 일반 플래그
        #
        # 일단 단발 이벤트로 저장.
        # 시작/종료 시간이 같다.
        # ───────────────────────

        if event_type in {
            "YELLOW_FLAG",
            "GREEN_FLAG",
            "BLUE_FLAG",
            "CHEQUERED_FLAG",
        }:
            add_period(event_type,event,event,)

    # 종료 메시지를 찾지 못한 구간은
    # end=NULL로 저장
    for (period_type,start_event,) in active.items():
        add_period(period_type,start_event,None,)

    db.flush()