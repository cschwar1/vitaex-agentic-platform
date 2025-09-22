from datetime import datetime
from typing import Any, Dict, List, Optional

JsonDict = Dict[str, Any]


def wearable_to_fhir_observation(user_id: str, metric: str, ts: str, value: float, unit: Optional[str] = None,
                                 device: Optional[str] = None, meta: Optional[JsonDict] = None) -> JsonDict:
    observation = {
        "resourceType": "Observation",
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
        "code": {"text": metric},
        "subject": {"reference": f"Patient/{user_id}"},
        "effectiveDateTime": ts,
        "valueQuantity": {"value": value, "unit": unit or "unit"},
        "device": {"display": device or "unknown"},
        "meta": meta or {}
    }
    return observation


def lab_to_fhir_observation(user_id: str, analyte: str, ts: str, value: float, unit: Optional[str] = None,
                            lab_name: Optional[str] = None, meta: Optional[JsonDict] = None) -> JsonDict:
    return {
        "resourceType": "Observation",
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
        "code": {"text": analyte},
        "subject": {"reference": f"Patient/{user_id}"},
        "effectiveDateTime": ts,
        "valueQuantity": {"value": value, "unit": unit or "unit"},
        "performer": [{"display": lab_name or "unknown"}],
        "meta": meta or {}
    }


def questionnaire_to_fhir(user_id: str, questionnaire_id: str, answers: List[JsonDict], authored: Optional[str] = None) -> JsonDict:
    return {
        "resourceType": "QuestionnaireResponse",
        "questionnaire": f"Questionnaire/{questionnaire_id}",
        "status": "completed",
        "subject": {"reference": f"Patient/{user_id}"},
        "authored": authored or datetime.utcnow().isoformat(),
        "item": answers
    }