import os
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx
from loguru import logger

from common.event_bus import EventBus
from common.models.fhir_mapper import lab_to_fhir_observation
from common.models.omop_mapper import fhir_observation_to_omop

JsonDict = Dict[str, Any]


class OmnosConnector:
    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None, bus: Optional[EventBus] = None):
        self.token = token or os.getenv("OMNOS_TOKEN", "")
        self.base_url = base_url or os.getenv("OMNOS_BASE_URL", "https://api.omnos.me/v1")
        self.bus = bus
        self.client = httpx.AsyncClient(timeout=30.0)

    async def fetch_user_results(self, user_id: str) -> List[JsonDict]:
        headers = {"Authorization": f"Bearer {self.token}"}
        r = await self.client.get(f"{self.base_url}/users/{user_id}/results", headers=headers)
        r.raise_for_status()
        return r.json().get("results", [])

    async def standardize_and_publish(self, user_id: str) -> int:
        results = await self.fetch_user_results(user_id)
        count = 0
        standard = []
        for res in results:
            ts = res.get("timestamp") or datetime.utcnow().isoformat()
            observation = lab_to_fhir_observation(user_id, res.get("analyte", "unknown"), ts, res.get("value"), unit=res.get("unit"), lab_name="Omnos", meta={"source": "omnos"})
            omop_row = fhir_observation_to_omop(observation)
            standard.append({"fhir": observation, "omop": omop_row})
            count += 1
        if self.bus:
            await self.bus.publish(
                topic="ingest.labs.standardized",
                event_type="labs.standardized",
                payload={"user_id": user_id, "meta": {"source": "omnos", "count": count}},
                user_id=user_id
            )
        logger.info(f"Standardized {count} Omnos results for user={user_id}")
        return count