from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.persistence.timeseries_client import TimeseriesClient
from common.privacy.consent import consent_store
from common.privacy.audit import audit_event

JsonDict = Dict[str, Any]


class DataIngestionAgent(BaseAgent):
    """
    Agent responsible for ingesting and persisting health data from various sources.
    
    Listens for standardized data events and persists measurements to TimescaleDB
    for time-series analysis and retrieval.
    """
    
    def __init__(self, bus):
        super().__init__(AgentConfig(
            name="data_ingestion_agent",
            subscribe_topics=[
                "ingest.wearables.raw",
                "ingest.wearables.standardized",
                "ingest.labs.raw",
                "ingest.labs.standardized",
                "ingest.questionnaire.standardized"
            ]
        ), bus)
        self.ts = TimeseriesClient()
        self._batch_size = 100  # Process in batches for efficiency

    async def _consent_guard(self, event: Event) -> bool:
        """Check if user has consented to data processing."""
        if not event.user_id:
            return True
        return consent_store.check(event.user_id, "data_processing")

    async def handle(self, event: Event) -> None:
        """Process incoming data events and persist to storage."""
        try:
            if event.topic == "ingest.wearables.standardized":
                await self._handle_wearables_data(event)
            elif event.topic == "ingest.labs.standardized":
                await self._handle_labs_data(event)
            elif event.topic == "ingest.questionnaire.standardized":
                await self._handle_questionnaire_data(event)
            elif event.topic == "ingest.wearables.raw":
                await self._handle_raw_wearables(event)
            elif event.topic == "ingest.labs.raw":
                await self._handle_raw_labs(event)
        except Exception as e:
            logger.error(f"Error processing event in {self.config.name}: {e}")
            await self.on_error(e, event.payload)

    async def _handle_wearables_data(self, event: Event) -> None:
        """Extract and persist wearable measurements from standardized event."""
        user_id = event.user_id or event.payload.get("user_id")
        if not user_id:
            logger.warning("No user_id in wearables event")
            return
        
        data = event.payload.get("data", [])
        provider = event.payload.get("provider", "unknown")
        measurements = []
        
        # Extract measurements from standardized FHIR observations
        for item in data:
            if isinstance(item, dict) and "fhir" in item:
                fhir_obs = item["fhir"]
                metric = fhir_obs.get("code", {}).get("text", "unknown")
                ts = fhir_obs.get("effectiveDateTime")
                value = fhir_obs.get("valueQuantity", {}).get("value")
                
                if ts and value is not None:
                    measurements.append({
                        "user_id": user_id,
                        "metric": metric,
                        "ts": ts,
                        "value": float(value),
                        "meta": {
                            "source": "wearables",
                            "provider": provider,
                            "unit": fhir_obs.get("valueQuantity", {}).get("unit"),
                            "device": fhir_obs.get("device", {}).get("display")
                        }
                    })
        
        # Persist measurements in batches
        if measurements:
            try:
                for i in range(0, len(measurements), self._batch_size):
                    batch = measurements[i:i + self._batch_size]
                    count = self.ts.insert_measurements(batch)
                    logger.info(f"Persisted {count} wearable measurements for user {user_id}")
                
                audit_event(
                    "ingestion.wearables.persisted",
                    user_id=user_id,
                    details={
                        "count": len(measurements),
                        "provider": provider
                    },
                    correlation_id=event.correlation_id
                )
            except Exception as e:
                logger.error(f"Failed to persist wearable data: {e}")
                raise
        else:
            logger.debug(f"No measurements to persist from wearables event")

    async def _handle_labs_data(self, event: Event) -> None:
        """Extract and persist lab measurements from standardized event."""
        user_id = event.user_id or event.payload.get("user_id")
        if not user_id:
            logger.warning("No user_id in labs event")
            return
        
        # Labs data might come as FHIR observations or OMOP measurements
        fhir_data = event.payload.get("fhir")
        omop_data = event.payload.get("omop")
        measurements = []
        
        if fhir_data:
            # Process FHIR observation
            metric = fhir_data.get("code", {}).get("text", "unknown")
            ts = fhir_data.get("effectiveDateTime")
            value = fhir_data.get("valueQuantity", {}).get("value")
            
            if ts and value is not None:
                measurements.append({
                    "user_id": user_id,
                    "metric": f"lab_{metric}",  # Prefix to distinguish from wearables
                    "ts": ts,
                    "value": float(value),
                    "meta": {
                        "source": "labs",
                        "lab": fhir_data.get("performer", [{}])[0].get("display", "unknown"),
                        "unit": fhir_data.get("valueQuantity", {}).get("unit")
                    }
                })
        
        if omop_data:
            # Process OMOP measurement
            metric = omop_data.get("measurement_source_value", "unknown")
            ts = omop_data.get("measurement_datetime")
            value = omop_data.get("value_as_number")
            
            if ts and value is not None:
                measurements.append({
                    "user_id": user_id,
                    "metric": f"lab_{metric}",
                    "ts": ts,
                    "value": float(value),
                    "meta": {
                        "source": "labs",
                        "omop_concept_id": omop_data.get("measurement_concept_id"),
                        "unit": omop_data.get("unit_source_value")
                    }
                })
        
        # Persist measurements
        if measurements:
            try:
                count = self.ts.insert_measurements(measurements)
                logger.info(f"Persisted {count} lab measurements for user {user_id}")
                
                audit_event(
                    "ingestion.labs.persisted",
                    user_id=user_id,
                    details={"count": len(measurements)},
                    correlation_id=event.correlation_id
                )
            except Exception as e:
                logger.error(f"Failed to persist lab data: {e}")
                raise

    async def _handle_questionnaire_data(self, event: Event) -> None:
        """Process and persist questionnaire responses as categorical data."""
        user_id = event.user_id or event.payload.get("user_id")
        if not user_id:
            logger.warning("No user_id in questionnaire event")
            return
        
        questionnaire_id = event.payload.get("questionnaire_id")
        fhir_response = event.payload.get("fhir", {})
        
        # Extract numeric answers as measurements
        measurements = []
        items = fhir_response.get("item", [])
        
        for item in items:
            # Look for numeric answers that can be tracked as time-series
            answer = item.get("answer", [{}])[0] if item.get("answer") else {}
            
            if "valueDecimal" in answer or "valueInteger" in answer:
                value = answer.get("valueDecimal") or answer.get("valueInteger")
                question_id = item.get("linkId", "unknown")
                
                measurements.append({
                    "user_id": user_id,
                    "metric": f"questionnaire_{questionnaire_id}_{question_id}",
                    "ts": fhir_response.get("authored", datetime.utcnow().isoformat()),
                    "value": float(value),
                    "meta": {
                        "source": "questionnaire",
                        "questionnaire_id": questionnaire_id,
                        "question": item.get("text", "")
                    }
                })
        
        if measurements:
            try:
                count = self.ts.insert_measurements(measurements)
                logger.info(f"Persisted {count} questionnaire measurements for user {user_id}")
                
                audit_event(
                    "ingestion.questionnaire.persisted",
                    user_id=user_id,
                    details={
                        "questionnaire_id": questionnaire_id,
                        "count": len(measurements)
                    },
                    correlation_id=event.correlation_id
                )
            except Exception as e:
                logger.error(f"Failed to persist questionnaire data: {e}")
                raise

    async def _handle_raw_wearables(self, event: Event) -> None:
        """
        Process raw wearable data by standardizing and republishing.
        
        Raw data needs to be converted to FHIR format before persistence.
        """
        user_id = event.user_id or event.payload.get("user_id")
        if not user_id:
            logger.warning("No user_id in raw wearables event")
            return
        
        raw_data = event.payload.get("data", [])
        provider = event.payload.get("provider", "unknown")
        
        # Standardize raw data (simplified example)
        standardized = []
        for point in raw_data:
            if isinstance(point, dict):
                # Attempt to extract common fields
                metric = point.get("type") or point.get("metric") or "unknown"
                value = point.get("value")
                timestamp = point.get("timestamp") or point.get("ts")
                
                if value is not None and timestamp:
                    standardized.append({
                        "metric": metric,
                        "value": value,
                        "timestamp": timestamp,
                        "unit": point.get("unit", "")
                    })
        
        if standardized:
            logger.debug(f"Standardized {len(standardized)} raw data points")
            
            # Publish standardized event for reprocessing
            await self.publish(
                "ingest.wearables.standardized",
                "wearables.standardized",
                payload={
                    "user_id": user_id,
                    "provider": provider,
                    "data": standardized,
                    "meta": {"standardized_from_raw": True}
                },
                user_id=user_id,
                correlation_id=event.correlation_id
            )

    async def _handle_raw_labs(self, event: Event) -> None:
        """
        Process raw lab data by standardizing and republishing.
        
        Raw lab data needs proper mapping to standard vocabularies.
        """
        user_id = event.user_id or event.payload.get("user_id")
        if not user_id:
            logger.warning("No user_id in raw labs event")
            return
        
        logger.debug(f"Received raw labs data for standardization")
        
        # For raw labs, standardization would involve:
        # 1. Mapping lab codes to standard vocabularies (LOINC)
        # 2. Normalizing units
        # 3. Validating reference ranges
        # This is simplified for the implementation
        
        # Publish request for standardization
        await self.publish(
            "ingest.labs.standardization.requested",
            "labs.standardization.request",
            payload=event.payload,
            user_id=user_id,
            correlation_id=event.correlation_id
        )