"""ORM models. Previous snapshots are RETAINED (never overwritten) so the
engine can compare current vs previous vs scheduled state on every cycle."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Train(Base):
    __tablename__ = "trains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    train_name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_code: Mapped[str | None] = mapped_column(String(16))
    source_name: Mapped[str | None] = mapped_column(String(128))
    destination_code: Mapped[str | None] = mapped_column(String(16))
    destination_name: Mapped[str | None] = mapped_column(String(128))
    run_days: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scheduled_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    scheduled_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_halts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32))  # running / not-started / reached / unknown
    # Per-train live-tracking switch (user controlled). When False the train
    # shows its last real snapshot and consumes zero external API calls.
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    route_points: Mapped[list["RoutePoint"]] = relationship(
        back_populates="train", cascade="all, delete-orphan", order_by="RoutePoint.sequence"
    )
    state_snapshots: Mapped[list["TrainStateSnapshot"]] = relationship(
        back_populates="train", cascade="all, delete-orphan", order_by="TrainStateSnapshot.timestamp"
    )
    weather_snapshots: Mapped[list["WeatherSnapshot"]] = relationship(
        back_populates="train", cascade="all, delete-orphan"
    )
    prediction_snapshots: Mapped[list["PredictionSnapshot"]] = relationship(
        back_populates="train", cascade="all, delete-orphan", order_by="PredictionSnapshot.timestamp"
    )
    events: Mapped[list["EventLog"]] = relationship(
        back_populates="train", cascade="all, delete-orphan", order_by="EventLog.timestamp"
    )
    simulation_state: Mapped["SimulationState | None"] = relationship(
        back_populates="train", cascade="all, delete-orphan", uselist=False
    )


class RoutePoint(Base):
    __tablename__ = "train_route_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    station_code: Mapped[str] = mapped_column(String(16))
    station_name: Mapped[str] = mapped_column(String(128))
    is_halt: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Observed/actual timings (real for LIVE mode, simulated for DEMO mode)
    actual_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delay_arrival: Mapped[float | None] = mapped_column(Float, nullable=True)
    delay_departure: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    platform: Mapped[str | None] = mapped_column(String(8), nullable=True)
    speed_to_next_kmph: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    train: Mapped[Train] = relationship(back_populates="route_points")


class TrainStateSnapshot(Base):
    __tablename__ = "train_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    current_station: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_station_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    current_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_delay_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_speed_kmph: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    distance_covered_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_source: Mapped[str] = mapped_column(String(16), default="LIVE")  # LIVE/CACHED/DEMO/SIMULATED

    train: Mapped[Train] = relationship(back_populates="state_snapshots")


class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall: Mapped[float | None] = mapped_column(Float, nullable=True)  # mm (last hour)
    precipitation_probability: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # m/s
    visibility: Mapped[float | None] = mapped_column(Float, nullable=True)  # km
    weather_condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weather_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    weather_risk_label: Mapped[str | None] = mapped_column(String(24), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)

    train: Mapped[Train] = relationship(back_populates="weather_snapshots")


class PredictionSnapshot(Base):
    __tablename__ = "prediction_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    current_delay: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_additional_delay: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_predicted_delay: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_lower_bound: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_upper_bound: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    prediction_mode: Mapped[str | None] = mapped_column(String(48), nullable=True)  # method label
    primary_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="DEMO")

    train: Mapped[Train] = relationship(back_populates="prediction_snapshots")
    factors: Mapped[list["PredictionFactor"]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )


class PredictionFactor(Base):
    __tablename__ = "prediction_factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("prediction_snapshots.id"), index=True)
    factor_name: Mapped[str] = mapped_column(String(64))
    factor_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    impact_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)  # delay/recovery/neutral
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)

    prediction: Mapped[PredictionSnapshot] = relationship(back_populates="factors")


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str] = mapped_column(String(32))  # arrival/departure/prediction/weather/simulation/system
    message: Mapped[str] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)

    train: Mapped[Train] = relationship(back_populates="events")


class ApiCache(Base):
    """Persistent cache of external API responses — protects the limited quota."""
    __tablename__ = "api_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(191), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimulationState(Base):
    """Virtual-clock bookkeeping for the designated DEMO train."""

    __tablename__ = "simulation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id"), unique=True)
    demo_delay_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    demo_last_sim_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    demo_tick_count: Mapped[int] = mapped_column(Integer, default=0)
    demo_anchor_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    train: Mapped[Train] = relationship(back_populates="simulation_state")
