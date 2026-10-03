"""Recovery estimation — a CORE differentiator of RailCast AI.

Definitions (documented assumptions, no fabricated railway truth):

- scheduled_running_minutes(section) = scheduled arrival(next halt)
    - scheduled departure(previous halt).
- ideal_running_minutes = distance / (scheduled_avg_speed * 1.15) * 60.
  The 1.15 multiplier allows running up to 15% above the train's scheduled
  average speed — a conservative stand-in for "making up time through speed".
- slack = max(0, scheduled - ideal)  → running-time slack of the section.
- dwell_recovery(halt) = max(0, scheduled_dwell - 2 min) * 0.5
  (intermediate halts only; at most half of the "excess" dwell is assumed
  recoverable, never below a 2-minute operational minimum).
- Classification per section: HIGH if slack ratio >= 18% of the scheduled
  running time, MEDIUM if >= 8%, otherwise LOW.

Bounded recovery: recovery = min(sum(estimated recoverable), current_delay,
MAX_RECOVERY_MINUTES). Recovery never exceeds the delay it would erase.
"""
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class SectionRecovery:
    from_station_code: str
    from_station_name: str
    to_station_code: str
    to_station_name: str
    distance_km: float
    scheduled_running_minutes: float
    ideal_running_minutes: float
    slack_minutes: float
    dwell_recovery_minutes: float
    total_recoverable_minutes: float
    classification: str  # HIGH / MEDIUM / LOW
    reason: str

    def to_dict(self) -> dict:
        return {
            "from_station_code": self.from_station_code,
            "from_station_name": self.from_station_name,
            "to_station_code": self.to_station_code,
            "to_station_name": self.to_station_name,
            "distance_km": round(self.distance_km, 1),
            "scheduled_running_minutes": round(self.scheduled_running_minutes, 1),
            "slack_minutes": round(self.slack_minutes, 1),
            "dwell_recovery_minutes": round(self.dwell_recovery_minutes, 1),
            "recovery_potential_minutes": round(self.total_recoverable_minutes, 1),
            "classification": self.classification,
            "reason": self.reason,
        }


@dataclass
class RecoveryEstimate:
    sections: list[SectionRecovery] = field(default_factory=list)
    raw_recoverable_minutes: float = 0.0
    applied_recovery_minutes: float = 0.0
    capped_by: str | None = None  # "current delay" / "max recovery cap" / None


def _minutes_between(start, end) -> float | None:
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds() / 60.0
    return delta if delta > 0 else None


def calculate_section_recovery(
    sections: list[dict],
    scheduled_avg_speed_kmph: float,
) -> list[SectionRecovery]:
    """`sections` = upcoming halt-to-halt sections, each dict with:
    from_code/from_name/to_code/to_name, distance_km,
    scheduled_running_minutes, scheduled_dwell_minutes (dwell at END halt,
    None for the final destination)."""
    results: list[SectionRecovery] = []
    efficiency = settings.recovery_efficiency
    for sec in sections:
        dist = sec.get("distance_km") or 0.0
        sched = sec.get("scheduled_running_minutes")
        if not sched or sched <= 0 or dist <= 0:
            continue
        avg = max(scheduled_avg_speed_kmph or 45.0, 20.0)
        ideal = dist / (avg * 1.15) * 60.0
        slack = max(0.0, sched - ideal)
        dwell = sec.get("scheduled_dwell_minutes")
        dwell_recovery = max(0.0, (dwell or 0.0) - 2.0) * 0.5 if dwell else 0.0
        recoverable = slack * efficiency + dwell_recovery

        ratio = slack / sched
        if ratio >= 0.18 or dwell_recovery >= 2.0:
            classification = "HIGH"
            reason = "generous estimated running-time margin" + (
                " and compressible halt dwell" if dwell_recovery >= 2.0 else ""
            )
        elif ratio >= 0.08:
            classification = "MEDIUM"
            reason = "moderate estimated running-time margin"
        else:
            classification = "LOW"
            reason = "tight estimated schedule — limited recovery headroom"

        results.append(
            SectionRecovery(
                from_station_code=sec["from_code"], from_station_name=sec["from_name"],
                to_station_code=sec["to_code"], to_station_name=sec["to_name"],
                distance_km=dist, scheduled_running_minutes=sched,
                ideal_running_minutes=ideal, slack_minutes=slack,
                dwell_recovery_minutes=dwell_recovery,
                total_recoverable_minutes=recoverable,
                classification=classification, reason=reason,
            )
        )
    return results


def calculate_recovery_potential(
    sections: list[SectionRecovery],
    current_delay_minutes: float,
    max_recovery: float | None = None,
) -> RecoveryEstimate:
    """Bounded recovery: never exceeds current delay or the configured cap."""
    cap = max_recovery if max_recovery is not None else settings.max_recovery_minutes
    raw = sum(s.total_recoverable_minutes for s in sections)
    estimate = RecoveryEstimate(sections=sections, raw_recoverable_minutes=raw)

    if current_delay_minutes <= 0:
        estimate.applied_recovery_minutes = 0.0
        estimate.capped_by = "train is not delayed"
        return estimate
    if raw <= 0:
        estimate.applied_recovery_minutes = 0.0
        return estimate

    applied = min(raw, current_delay_minutes, cap)
    if applied == current_delay_minutes < raw:
        estimate.capped_by = "current delay (recovery cannot exceed the delay)"
    elif applied == cap < raw:
        estimate.capped_by = "configured maximum recovery"
    estimate.applied_recovery_minutes = applied
    return estimate
