from typing import Any, Dict, List, Optional
from datetime import datetime

from common.event_bus import EventBus
from common.models.fhir_mapper import questionnaire_to_fhir

JsonDict = Dict[str, Any]


class QuestionnaireProcessor:
    def __init__(self, bus: EventBus):
        self.bus = bus

    async def process(self, user_id: str, questionnaire_id: str, answers: List[JsonDict], authored: Optional[str] = None) -> Dict[str, Any]:
        fhir = questionnaire_to_fhir(user_id, questionnaire_id, answers, authored or datetime.utcnow().isoformat())
        await self.bus.publish(
            topic="ingest.questionnaire.standardized",
            event_type="questionnaire.standardized",
            payload={"user_id": user_id, "questionnaire_id": questionnaire_id, "fhir": fhir},
            user_id=user_id
        )
        return {"status": "ok", "questionnaire_id": questionnaire_id}