from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Drop-in replacement for the existing project model file.
# In the real project this Base comes from app.db.
from app.db import Base


class SessionType(str, enum.Enum):
    FP1 = "FP1"
    FP2 = "FP2"
    FP3 = "FP3"
    Q = "Q"
    SQ = "SQ"
    S = "S"
    R = "R"


class MediaAsset(Base):
    """Image/file metadata only. Store actual bytes in object storage/static storage."""
    
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    public_url: Mapped[str | None] = mapped_column(String(1000))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    alt_text: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(String(255))
    license_note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class Country(Base):
    __tablename__ = "countries"

    # ISO 3166-1 alpha-2 when possible (GB, IT, JP, ...)
    code: Mapped[str] = mapped_column(String(2), primary_key=True, autoincrement=False)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ko: Mapped[str | None] = mapped_column(String(120))
    demonym_en: Mapped[str | None] = mapped_column(String(120))
    flag_image_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("media_assets.id", ondelete="SET NULL"),
    )


class Season(Base):
    __tablename__ = "seasons"

    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    total_rounds: Mapped[int | None] = mapped_column(SmallInteger)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    regulations_era: Mapped[str | None] = mapped_column(String(100))


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    driver_ref: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    permanent_number: Mapped[int | None] = mapped_column(SmallInteger)
    abbreviation: Mapped[str | None] = mapped_column(String(3))
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    # Keep legacy text for upstream compatibility; nationality_code is normalized.
    nationality: Mapped[str | None] = mapped_column(String(80))
    nationality_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="SET NULL"),
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date)


class Constructor(Base):
    __tablename__ = "constructors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    constructor_ref: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    nationality: Mapped[str | None] = mapped_column(String(80))
    nationality_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="SET NULL"),
    )


class Circuit(Base):
    __tablename__ = "circuits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    circuit_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    name_ko: Mapped[str | None] = mapped_column(String(180))
    city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))  # legacy upstream text
    country_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="SET NULL"),
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    # Kept for backward compatibility/fallback. New code should prefer circuit_layouts.length_meters.
    length_meters: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str | None] = mapped_column(String(80))
    opening_year: Mapped[int | None] = mapped_column(SmallInteger)


class CircuitLayout(Base):
    """Track geometry/layout metadata that may change over time at the same circuit."""

    __tablename__ = "circuit_layouts"
    __table_args__ = (
        UniqueConstraint("layout_ref", name="uq_circuit_layout_ref"),
        Index("ix_circuit_layout_current", "circuit_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    circuit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("circuits.id", ondelete="CASCADE"),
        nullable=False,
    )
    layout_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    layout_name: Mapped[str | None] = mapped_column(String(180))
    valid_from_year: Mapped[int | None] = mapped_column(SmallInteger)
    valid_to_year: Mapped[int | None] = mapped_column(SmallInteger)
    length_meters: Mapped[int | None] = mapped_column(Integer)
    corners: Mapped[int | None] = mapped_column(SmallInteger)
    map_image_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("media_assets.id", ondelete="SET NULL"),
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

class CircuitMedia(Base):
    __tablename__ = "circuit_media"

    __table_args__ = (
        UniqueConstraint(
            "circuit_layout_id",
            "media_asset_id",
            name="uq_circuit_media_asset",
        ),
        Index(
            "ix_circuit_media_layout_type",
            "circuit_layout_id",
            "image_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    circuit_layout_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "circuit_layouts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    media_asset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "media_assets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    image_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    display_order: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
    )

class SeasonDriverEntry(Base):
    __tablename__ = "season_driver_entries"
    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "driver_id",
            "constructor_id",
            name="uq_season_driver_constructor",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("seasons.year", ondelete="CASCADE"),
        nullable=False,
    )
    driver_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("drivers.id", ondelete="CASCADE"),
        nullable=False,
    )
    constructor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("constructors.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Legacy team color field. Kept for compatibility; canonical team color is season_constructor_entries.color.
    color: Mapped[str | None] = mapped_column(String(12))
    car_number: Mapped[int | None] = mapped_column(SmallInteger)
    start_round: Mapped[int | None] = mapped_column(SmallInteger)
    end_round: Mapped[int | None] = mapped_column(SmallInteger)
    is_primary_driver: Mapped[bool | None] = mapped_column(Boolean)
    portrait_image_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("media_assets.id", ondelete="SET NULL"),
    )


class SeasonConstructorEntry(Base):
    __tablename__ = "season_constructor_entries"
    __table_args__ = (
        UniqueConstraint("season_year", "constructor_id", name="uq_season_constructor"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("seasons.year", ondelete="CASCADE"),
        nullable=False,
    )
    constructor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("constructors.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_name: Mapped[str | None] = mapped_column(String(180))
    engine_name: Mapped[str | None] = mapped_column(String(180))
    color: Mapped[str | None] = mapped_column(String(12))
    logo_image_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("media_assets.id", ondelete="SET NULL"),
    )


class GrandPrix(Base):
    __tablename__ = "grand_prix"
    __table_args__ = (
        UniqueConstraint("season_year", "round_number", name="uq_gp_season_round"),
        Index("ix_gp_season_date", "season_year", "weekend_start_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("seasons.year", ondelete="CASCADE"),
        nullable=False,
    )
    circuit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("circuits.id"),
        nullable=False,
    )
    circuit_layout_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("circuit_layouts.id", ondelete="SET NULL"),
    )
    # GP/event nationality should not always be inferred from circuit country.
    country_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="SET NULL"),
    )
    round_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    official_name: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    display_name_ko: Mapped[str | None] = mapped_column(String(180))
    event_format: Mapped[str | None] = mapped_column(String(40))
    weekend_start_date: Mapped[date | None] = mapped_column(Date)
    weekend_end_date: Mapped[date | None] = mapped_column(Date)
    # Needed before the race has happened. Actual completed laps remain in sessions.total_laps.
    scheduled_laps: Mapped[int | None] = mapped_column(SmallInteger)
    scheduled_race_distance_meters: Mapped[int | None] = mapped_column(Integer)
    winning_driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("drivers.id"))
    winning_constructor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("constructors.id"),
    )
    status: Mapped[str | None] = mapped_column(String(40), default="scheduled")


class GrandPrixTyreAllocation(Base):
    __tablename__ = "grand_prix_tyre_allocations"
    __table_args__ = (
        UniqueConstraint(
            "grand_prix_id",
            "compound_code",
            "weekend_role",
            name="uq_gp_tyre_compound_role",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    grand_prix_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("grand_prix.id", ondelete="CASCADE"),
        nullable=False,
    )
    # VARCHAR instead of enum so future compounds (C6, etc.) do not require a schema migration.
    compound_code: Mapped[str] = mapped_column(String(16), nullable=False)
    weekend_role: Mapped[str] = mapped_column(String(20), nullable=False)  # HARD/MEDIUM/SOFT/INTERMEDIATE/WET
    sets_per_driver: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(Text)


class DriverStanding(Base):
    __tablename__ = "driver_standings"
    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "after_round",
            "driver_id",
            name="uq_driver_standing_round",
        ),
        Index("ix_driver_standings_round", "season_year", "after_round", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("seasons.year", ondelete="CASCADE"),
        nullable=False,
    )
    after_round: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    driver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("drivers.id"), nullable=False)
    constructor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("constructors.id"))
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    wins: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    podiums: Mapped[int | None] = mapped_column(SmallInteger)


class ConstructorStanding(Base):
    __tablename__ = "constructor_standings"
    __table_args__ = (
        UniqueConstraint(
            "season_year",
            "after_round",
            "constructor_id",
            name="uq_constructor_standing_round",
        ),
        Index("ix_constructor_standings_round", "season_year", "after_round", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("seasons.year", ondelete="CASCADE"),
        nullable=False,
    )
    after_round: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    constructor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("constructors.id"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    wins: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    podiums: Mapped[int | None] = mapped_column(SmallInteger)


class SessionModel(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("grand_prix_id", "type", name="uq_gp_session_type"),
        Index("ix_session_gp_start", "grand_prix_id", "scheduled_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    grand_prix_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("grand_prix.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[SessionType] = mapped_column(
        Enum(SessionType, name="session_type", native_enum=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    status: Mapped[str | None] = mapped_column(String(40), default="scheduled")
    total_laps: Mapped[int | None] = mapped_column(SmallInteger)

    entries: Mapped[list[SessionEntry]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class SessionEntry(Base):
    __tablename__ = "session_entries"
    __table_args__ = (
        UniqueConstraint("session_id", "driver_id", name="uq_session_driver"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    driver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("drivers.id"), nullable=False)
    constructor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("constructors.id"),
        nullable=False,
    )
    racing_number: Mapped[int | None] = mapped_column(SmallInteger)
    abbreviation: Mapped[str | None] = mapped_column(String(3))
    grid_position: Mapped[int | None] = mapped_column(SmallInteger)

    session: Mapped[SessionModel] = relationship(back_populates="entries")
    result: Mapped[SessionResult | None] = relationship(
        back_populates="session_entry",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SessionResult(Base):
    __tablename__ = "session_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_entry_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("session_entries.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    classified_position: Mapped[int | None] = mapped_column(SmallInteger)
    displayed_position: Mapped[str | None] = mapped_column(String(8))
    grid_position: Mapped[int | None] = mapped_column(SmallInteger)
    finishing_position: Mapped[int | None] = mapped_column(SmallInteger)
    points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    status: Mapped[str | None] = mapped_column(String(120))
    laps_completed: Mapped[int | None] = mapped_column(SmallInteger)
    total_time_us: Mapped[int | None] = mapped_column(BigInteger)
    gap_to_winner_us: Mapped[int | None] = mapped_column(BigInteger)
    fastest_lap_number: Mapped[int | None] = mapped_column(SmallInteger)
    fastest_lap_time: Mapped[int | None] = mapped_column(BigInteger)
    q1_time_us: Mapped[int | None] = mapped_column(BigInteger)
    q2_time_us: Mapped[int | None] = mapped_column(BigInteger)
    q3_time_us: Mapped[int | None] = mapped_column(BigInteger)

    session_entry: Mapped[SessionEntry] = relationship(back_populates="result")


class DriverOfTheDay(Base):
    __tablename__ = "driver_of_the_day"

    grand_prix_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("grand_prix.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )
    driver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("drivers.id"), nullable=False)
    vote_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    source: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(Text)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class Lap(Base):
    __tablename__ = "laps"
    __table_args__ = (
        UniqueConstraint("session_entry_id", "lap_number", name="uq_entry_lap"),
        Index("ix_laps_entry_number", "session_entry_id", "lap_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_entry_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("session_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    lap_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    position: Mapped[int | None] = mapped_column(SmallInteger)
    lap_time_us: Mapped[int | None] = mapped_column(BigInteger)
    sector1_time_us: Mapped[int | None] = mapped_column(BigInteger)
    sector2_time_us: Mapped[int | None] = mapped_column(BigInteger)
    sector3_time_us: Mapped[int | None] = mapped_column(BigInteger)
    gap_to_leader_us: Mapped[int | None] = mapped_column(BigInteger)
    interval_to_ahead_us: Mapped[int | None] = mapped_column(BigInteger)
    compound: Mapped[str | None] = mapped_column(String(24))
    tyre_life_laps: Mapped[int | None] = mapped_column(SmallInteger)
    stint_number: Mapped[int | None] = mapped_column(SmallInteger)
    pit_in_time_us: Mapped[int | None] = mapped_column(BigInteger)
    pit_out_time_us: Mapped[int | None] = mapped_column(BigInteger)
    track_status: Mapped[str | None] = mapped_column(String(32))
    # FastF1 Laps speed points (km/h). speed_st_kph directly supports the API speedtrap field.
    speed_i1_kph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    speed_i2_kph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    speed_fl_kph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    speed_st_kph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))


class TyreStint(Base):
    __tablename__ = "tyre_stints"
    __table_args__ = (
        UniqueConstraint("session_entry_id", "stint_number", name="uq_entry_stint"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_entry_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("session_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    stint_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    compound: Mapped[str | None] = mapped_column(String(24))
    start_lap: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    end_lap: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    total_laps: Mapped[int | None] = mapped_column(
        SmallInteger,
        Computed("end_lap - start_lap + 1", persisted=True),
        nullable=True,
    )
    starting_tyre_life: Mapped[int | None] = mapped_column(SmallInteger)
    ending_tyre_life: Mapped[int | None] = mapped_column(SmallInteger)
    fresh_tyre: Mapped[bool | None] = mapped_column(Boolean)


class PitStop(Base):
    __tablename__ = "pit_stops"
    __table_args__ = (
        UniqueConstraint("session_entry_id", "stop_number", name="uq_entry_stop"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_entry_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("session_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    stop_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    lap_number: Mapped[int | None] = mapped_column(SmallInteger)
    pit_entry_time_us: Mapped[int | None] = mapped_column(BigInteger)
    pit_exit_time_us: Mapped[int | None] = mapped_column(BigInteger)
    pit_lane_duration_us: Mapped[int | None] = mapped_column(BigInteger)
    stationary_duration_us: Mapped[int | None] = mapped_column(BigInteger)
    compound_before: Mapped[str | None] = mapped_column(String(24))
    compound_after: Mapped[str | None] = mapped_column(String(24))


class WeatherSample(Base):
    __tablename__ = "weather_samples"
    __table_args__ = (
        UniqueConstraint("session_id", "session_time_us", name="uq_weather_session_time"),
        Index("ix_weather_session_time", "session_id", "session_time_us"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sample_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    session_time_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    air_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    track_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    humidity_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    pressure_hpa: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    wind_speed_mps: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    wind_direction_deg: Mapped[int | None] = mapped_column(SmallInteger)
    rainfall: Mapped[bool | None] = mapped_column(Boolean)


class RaceControlEvent(Base):
    __tablename__ = "race_control_events"
    __table_args__ = (
        Index("ix_rce_session_time", "session_id", "session_time_us"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    lap_number: Mapped[int | None] = mapped_column(SmallInteger)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    session_time_us: Mapped[int | None] = mapped_column(BigInteger)
    category: Mapped[str | None] = mapped_column(String(80))
    event_type: Mapped[str | None] = mapped_column(String(80))
    flag: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text, nullable=False)


class RacePeriod(Base):
    __tablename__ = "race_periods"
    __table_args__ = (
        Index("ix_race_period_session_start", "session_id", "start_time_us"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Recommended values: YELLOW, RED, SAFETY_CAR, VSC, GREEN, etc.
    period_type: Mapped[str] = mapped_column(String(40), nullable=False)
    start_time_us: Mapped[int | None] = mapped_column(BigInteger)
    end_time_us: Mapped[int | None] = mapped_column(BigInteger)
    start_lap: Mapped[int | None] = mapped_column(SmallInteger)
    end_lap: Mapped[int | None] = mapped_column(SmallInteger)
    start_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("race_control_events.id", ondelete="SET NULL"),
    )
    end_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("race_control_events.id", ondelete="SET NULL"),
    )


class CircuitRecord(Base):

    __tablename__ = "circuit_records"
    __table_args__ = (
        UniqueConstraint("circuit_layout_id", "record_type", name="uq_layout_record_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    circuit_layout_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("circuit_layouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    record_type: Mapped[str] = mapped_column(String(32), nullable=False)
    driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("drivers.id", ondelete="SET NULL"))
    constructor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("constructors.id", ondelete="SET NULL"),
    )
    grand_prix_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("grand_prix.id", ondelete="SET NULL"),
    )
    record_year: Mapped[int | None] = mapped_column(SmallInteger)
    lap_time_us: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(Text)

class GrandPrixSyncState(Base):
    __tablename__ = "grand_prix_sync_state"

    grand_prix_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("grand_prix.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )

    pre_event_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    last_live_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    post_event_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )