from typing import Any, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.privacy.consent import consent_store
from common.privacy.audit import audit_event

JsonDict = Dict[str, Any]


@dataclass
class Scenario:
    sleep_minutes_delta: int = 0
    activity_minutes_delta: int = 0
    stress_reduction: float = 0.0  # 0 to 1 scale


class VitalitySimulationAgent(BaseAgent):
    def __init__(self, bus):
        super().__init__(AgentConfig(
            name="vitality_simulation_agent",
            subscribe_topics=["simulation.vitality.requested"]
        ), bus)

    async def _consent_guard(self, event: Event) -> bool:
        if not event.user_id:
            return True
        return consent_store.check(event.user_id, "personalization")

    async def handle(self, event: Event) -> None:
        user_id = event.user_id or "unknown"
        payload = event.payload or {}
        scenario = Scenario(
            sleep_minutes_delta=int(payload.get("sleep_minutes_delta", 0)),
            activity_minutes_delta=int(payload.get("activity_minutes_delta", 0)),
            stress_reduction=float(payload.get("stress_reduction", 0.0)),
        )

        # Simple interpretable model: increased sleep and activity and stress reduction improve HRV proxy and vitality
        base_vitality = float(payload.get("current_vitality", 0.6))
        new_vitality = base_vitality + (scenario.sleep_minutes_delta / 60.0) * 0.05 + (scenario.activity_minutes_delta / 60.0) * 0.05 + scenario.stress_reduction * 0.07
        new_vitality = max(0.0, min(new_vitality, 1.0))

        result = {
            "user_id": user_id,
            "baseline_vitality": base_vitality,
            "new_vitality": round(new_vitality, 3),
            "estimated_changes": {
                "hrv": round((new_vitality - base_vitality) * 15.0, 2)
            },
            "disclaimer": "This is a general wellness simulation, not a medical diagnosis or treatment recommendation."
        }

        audit_event("simulation.vitality.completed", user_id=user_id, details=result, correlation_id=event.correlation_id)

        await self.publish(
            topic="simulation.vitality.completed",
            event_type="simulation.completed",
            payload=result,
            user_id=user_id,
            correlation_id=event.correlation_id
        )