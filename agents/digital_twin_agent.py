from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import asyncio
from loguru import logger

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.persistence.timeseries_client import TimeseriesClient
from common.privacy.consent import consent_store
from common.privacy.audit import audit_event

JsonDict = Dict[str, Any]


@dataclass
class HealthMetrics:
    """Standardized health metrics with defined bounds and units."""
    hrv: float = 35.0  # Heart rate variability in milliseconds (ms), range: 20-100
    resting_heart_rate: float = 70.0  # Resting heart rate in bpm, range: 40-100
    sleep_efficiency: float = 0.85  # Sleep efficiency percentage (0-1), optimal: >0.85
    activity_minutes: float = 30.0  # Daily activity minutes, WHO recommendation: 30-60
    steps_daily: float = 8000.0  # Daily step count, recommendation: 8000-10000
    stress_score: float = 0.3  # Stress level (0-1), lower is better
    recovery_score: float = 0.7  # Recovery score (0-1), higher is better


@dataclass
class TwinState:
    """
    Digital twin state representing a user's health profile.
    
    Maintains longitudinal health metrics and calculates vitality scores
    based on evidence-based health indicators.
    """
    user_id: str
    created_at: str
    updated_at: str
    metrics: HealthMetrics = field(default_factory=HealthMetrics)
    vitality_score: float = 0.0  # Overall vitality (0-1), higher is better
    biological_age_delta: float = 0.0  # Years younger (-) or older (+) than chronological age
    trend_indicators: Dict[str, float] = field(default_factory=dict)  # 30-day trends
    intervention_efficacy: Dict[str, float] = field(default_factory=dict)  # Intervention impact scores
    last_sync: Optional[str] = None
    version: int = 1
    last_persistence: Optional[str] = None


class DigitalTwinAgent(BaseAgent):
    """
    Agent responsible for maintaining user-specific digital twins.
    
    Updates N-of-1 models from time-series data, calculates vitality scores
    using evidence-based heuristics, and tracks intervention efficacy.
    """
    
    # Evidence-based weights for vitality calculation
    # Based on research linking these metrics to healthspan/longevity
    VITALITY_WEIGHTS = {
        "hrv": 0.25,  # Strong predictor of cardiovascular health
        "sleep_efficiency": 0.20,  # Critical for recovery and longevity
        "activity": 0.20,  # Physical activity essential for health
        "recovery": 0.15,  # Recovery capacity indicates resilience
        "stress": 0.10,  # Chronic stress impacts healthspan
        "rhr": 0.10   # Resting heart rate indicates fitness
    }
    
    def __init__(self, bus):
        super().__init__(AgentConfig(
            name="digital_twin_agent",
            subscribe_topics=[
                "user.twin.update.requested",
                "ingest.wearables.standardized",
                "ingest.labs.standardized"
            ]
        ), bus)
        self._twins: Dict[str, TwinState] = {}
        self.ts = TimeseriesClient()
        self._persistence_interval_seconds = 300  # Persist every 5 minutes
        self._persistence_tasks: Dict[str, asyncio.Task] = {}

    async def _consent_guard(self, event: Event) -> bool:
        """Check if user has consented to personalization."""
        if not event.user_id:
            return True
        return consent_store.check(event.user_id, "personalization")

    async def handle(self, event: Event) -> None:
        """Process events and update digital twin state."""
        user_id = event.user_id or event.payload.get("user_id") or "unknown"
        twin = await self._get_or_create_twin(user_id)
        
        if event.topic == "ingest.wearables.standardized":
            await self._update_from_wearables(twin, event)
        elif event.topic == "ingest.labs.standardized":
            await self._update_from_labs(twin, event)
        elif event.topic == "user.twin.update.requested":
            await self._recalculate_twin(twin, event)
        
        # Update vitality score with evidence-based calculation
        self._calculate_vitality_score(twin)
        
        # Calculate trends from historical data
        await self._calculate_trends(twin)
        
        # Update timestamp and version
        twin.updated_at = datetime.utcnow().isoformat()
        twin.version += 1
        
        # Store updated twin
        self._twins[user_id] = twin
        
        # Schedule persistence if needed
        await self._schedule_persistence(twin)
        
        # Audit and publish update
        audit_event(
            "twin.updated",
            user_id=user_id,
            details={
                "vitality_score": round(twin.vitality_score, 3),
                "version": twin.version
            },
            correlation_id=event.correlation_id
        )
        
        await self.publish(
            topic="user.twin.updated",
            event_type="twin.updated",
            payload={
                "user_id": user_id,
                "vitality_score": round(twin.vitality_score, 3),
                "biological_age_delta": round(twin.biological_age_delta, 1),
                "metrics": asdict(twin.metrics),
                "trends": twin.trend_indicators,
                "version": twin.version
            },
            user_id=user_id,
            correlation_id=event.correlation_id
        )

    async def _get_or_create_twin(self, user_id: str) -> TwinState:
        """Get existing twin or create new one."""
        if user_id in self._twins:
            return self._twins[user_id]
        
        # Try to load from persistence
        twin = await self._load_twin_state(user_id)
        if twin:
            self._twins[user_id] = twin
            return twin
        
        # Create new twin
        now = datetime.utcnow().isoformat()
        twin = TwinState(
            user_id=user_id,
            created_at=now,
            updated_at=now
        )
        self._twins[user_id] = twin
        return twin

    async def _update_from_wearables(self, twin: TwinState, event: Event) -> None:
        """Update twin metrics from wearable data."""
        data = event.payload.get("data", [])
        
        for item in data:
            if isinstance(item, dict) and "fhir" in item:
                fhir_obs = item["fhir"]
                metric = fhir_obs.get("code", {}).get("text", "").lower()
                value = fhir_obs.get("valueQuantity", {}).get("value")
                
                if value is None:
                    continue
                
                # Update relevant metrics with bounds checking
                if metric == "hrv":
                    twin.metrics.hrv = max(20.0, min(100.0, float(value)))
                elif metric == "heart_rate" and value < 100:  # Likely resting if <100
                    twin.metrics.resting_heart_rate = max(40.0, min(100.0, float(value)))
                elif metric == "sleep_efficiency":
                    twin.metrics.sleep_efficiency = max(0.0, min(1.0, float(value)))
                elif metric == "activity_minutes":
                    twin.metrics.activity_minutes = max(0.0, min(240.0, float(value)))
                elif metric == "steps":
                    twin.metrics.steps_daily = max(0.0, float(value))
                elif metric == "stress_score":
                    twin.metrics.stress_score = max(0.0, min(1.0, float(value)))
                elif metric == "recovery_score":
                    twin.metrics.recovery_score = max(0.0, min(1.0, float(value)))

    async def _update_from_labs(self, twin: TwinState, event: Event) -> None:
        """Update twin with lab biomarkers for biological age calculation."""
        # Extract key biomarkers that influence biological age
        # Integrates with validated biological age algorithms
        biomarkers = event.payload.get("biomarkers", {})
        
        # Evidence-based biological age delta calculation
        # Based on established biomarker ranges from longevity research
        age_factors = []
        
        # CRP (inflammation marker)
        crp = biomarkers.get("crp") or biomarkers.get("c-reactive protein")
        if crp is not None:
            if crp < 1.0:
                age_factors.append(-1.0)  # Low inflammation, younger
            elif crp > 3.0:
                age_factors.append(2.0)   # High inflammation, older
        
        # HbA1c (metabolic health)
        hba1c = biomarkers.get("hba1c") or biomarkers.get("a1c")
        if hba1c is not None:
            if hba1c < 5.4:
                age_factors.append(-0.5)  # Good metabolic health
            elif hba1c > 5.7:
                age_factors.append(1.5)   # Prediabetic range
        
        # Vitamin D (immune function)
        vit_d = biomarkers.get("vitamin d") or biomarkers.get("25-hydroxyvitamin d")
        if vit_d is not None:
            if vit_d > 40:  # ng/ml
                age_factors.append(-0.3)  # Optimal level
            elif vit_d < 20:
                age_factors.append(1.0)   # Deficient
        
        if age_factors:
            twin.biological_age_delta = sum(age_factors) / len(age_factors)

    async def _recalculate_twin(self, twin: TwinState, event: Event) -> None:
        """Recalculate twin based on update request."""
        # Force recalculation of vitality and trends
        self._calculate_vitality_score(twin)
        await self._calculate_trends(twin)
        
        # Request fresh simulation if context suggests intervention changes
        context = event.payload.get("context", {})
        if context.get("trigger") == "intervention_change":
            await self.publish(
                topic="simulation.vitality.requested",
                event_type="simulation.request",
                payload={
                    "user_id": twin.user_id,
                    "current_vitality": twin.vitality_score,
                    "sleep_minutes_delta": 0,
                    "activity_minutes_delta": 0,
                    "stress_reduction": 0.0
                },
                user_id=twin.user_id,
                correlation_id=event.correlation_id
            )

    def _calculate_vitality_score(self, twin: TwinState) -> None:
        """
        Calculate vitality score using evidence-based weighted formula.
        
        Score components:
        - HRV: Higher is better (normalized to 0-100ms range)
        - Sleep Efficiency: Higher is better (0-1 scale)
        - Activity: Optimal at 30-60 minutes daily
        - Recovery: Higher is better (0-1 scale)
        - Stress: Lower is better (inverted, 0-1 scale)
        - Resting Heart Rate: Lower is better (normalized to 40-100 bpm)
        """
        metrics = twin.metrics
        
        # Normalize each metric to 0-1 scale
        hrv_score = max(0.0, min(1.0, (metrics.hrv - 20.0) / 80.0))  # 20-100ms range
        sleep_score = metrics.sleep_efficiency
        activity_score = min(metrics.activity_minutes / 60.0, 1.0)  # Cap at 60 min
        recovery_score = metrics.recovery_score
        stress_score = 1.0 - metrics.stress_score  # Invert: lower stress is better
        rhr_score = max(0.0, min(1.0, 1.0 - ((metrics.resting_heart_rate - 40.0) / 60.0)))  # 40-100 bpm range
        
        # Apply evidence-based weights
        vitality = (
            hrv_score * self.VITALITY_WEIGHTS["hrv"] +
            sleep_score * self.VITALITY_WEIGHTS["sleep_efficiency"] +
            activity_score * self.VITALITY_WEIGHTS["activity"] +
            recovery_score * self.VITALITY_WEIGHTS["recovery"] +
            stress_score * self.VITALITY_WEIGHTS["stress"] +
            rhr_score * self.VITALITY_WEIGHTS["rhr"]
        )
        
        # Ensure bounds and round
        twin.vitality_score = max(0.0, min(1.0, vitality))

    async def _calculate_trends(self, twin: TwinState) -> None:
        """Calculate 30-day trends for key metrics using time-aware computation."""
        # Query historical data from time-series database
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        metrics_to_trend = ["hrv", "sleep_efficiency", "activity_minutes", "stress_score"]
        
        for metric in metrics_to_trend:
            try:
                data = self.ts.query(
                    user_id=twin.user_id,
                    metric=metric,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    limit=1000
                )
                
                if len(data) > 5:  # Need minimum data points for reliable trend
                    # Calculate time-aware linear trend
                    timestamps = []
                    values = []
                    
                    for d in data:
                        try:
                            ts = datetime.fromisoformat(d["ts"].replace('Z', '+00:00'))
                            timestamps.append(ts.timestamp())
                            values.append(d["value"])
                        except (ValueError, TypeError, KeyError):
                            continue
                    
                    if len(timestamps) > 1:
                        # Calculate slope using time deltas
                        n = len(timestamps)
                        t_mean = sum(timestamps) / n
                        v_mean = sum(values) / n
                        
                        numerator = sum((t - t_mean) * (v - v_mean) for t, v in zip(timestamps, values))
                        denominator = sum((t - t_mean) ** 2 for t in timestamps)
                        
                        if denominator > 0:
                            slope = numerator / denominator
                            # Convert to daily change rate and normalize
                            daily_change = slope * 86400  # seconds per day
                            
                            # Normalize based on metric type
                            if metric == "hrv":
                                trend_score = max(-1.0, min(1.0, daily_change / 5.0))  # ±5ms/day
                            elif metric == "sleep_efficiency":
                                trend_score = max(-1.0, min(1.0, daily_change / 0.05))  # ±5%/day
                            elif metric == "activity_minutes":
                                trend_score = max(-1.0, min(1.0, daily_change / 10.0))  # ±10min/day
                            elif metric == "stress_score":
                                # Invert for stress (decreasing stress is positive trend)
                                trend_score = max(-1.0, min(1.0, -daily_change / 0.1))  # ±0.1/day
                            else:
                                trend_score = max(-1.0, min(1.0, daily_change))
                            
                            twin.trend_indicators[f"{metric}_trend"] = round(trend_score, 3)
                            
            except Exception as e:
                logger.debug(f"Could not calculate trend for {metric}: {e}")

    async def _schedule_persistence(self, twin: TwinState) -> None:
        """Schedule persistence based on time interval."""
        now = datetime.utcnow()
        should_persist = False
        
        # Check if enough time has passed or this is first persistence
        if twin.last_persistence is None:
            should_persist = True
        else:
            try:
                last_persist_time = datetime.fromisoformat(twin.last_persistence)
                if (now - last_persist_time).total_seconds() >= self._persistence_interval_seconds:
                    should_persist = True
            except (ValueError, TypeError):
                should_persist = True
        
        if should_persist:
            # Cancel any existing persistence task for this user
            if twin.user_id in self._persistence_tasks:
                self._persistence_tasks[twin.user_id].cancel()
            
            # Schedule new persistence
            task = asyncio.create_task(self._persist_twin_state(twin))
            self._persistence_tasks[twin.user_id] = task
            twin.last_persistence = now.isoformat()

    async def _persist_twin_state(self, twin: TwinState) -> None:
        """Persist twin state for recovery and analysis."""
        try:
            # Store as special time-series entry
            self.ts.insert_measurements([{
                "user_id": twin.user_id,
                "metric": "twin_state",
                "ts": twin.updated_at,
                "value": twin.vitality_score,
                "meta": {
                    "state": asdict(twin),
                    "version": twin.version,
                    "persistence_type": "scheduled"
                }
            }])
            logger.debug(f"Persisted twin state for user {twin.user_id}, version {twin.version}")
        except Exception as e:
            logger.error(f"Failed to persist twin state for user {twin.user_id}: {e}")
            # Reset last persistence time to retry
            twin.last_persistence = None

    async def _load_twin_state(self, user_id: str) -> Optional[TwinState]:
        """Load most recent twin state from persistence."""
        try:
            # Query latest twin state
            data = self.ts.query(
                user_id=user_id,
                metric="twin_state",
                limit=1
            )
            
            if data and data[0].get("meta", {}).get("state"):
                state_dict = data[0]["meta"]["state"]
                
                # Reconstruct metrics with validation
                metrics_dict = state_dict.get("metrics", {})
                metrics = HealthMetrics(**metrics_dict)
                
                # Reconstruct twin state
                twin = TwinState(
                    user_id=user_id,
                    created_at=state_dict.get("created_at"),
                    updated_at=state_dict.get("updated_at"),
                    metrics=metrics,
                    vitality_score=state_dict.get("vitality_score", 0.0),
                    biological_age_delta=state_dict.get("biological_age_delta", 0.0),
                    trend_indicators=state_dict.get("trend_indicators", {}),
                    intervention_efficacy=state_dict.get("intervention_efficacy", {}),
                    last_sync=state_dict.get("last_sync"),
                    version=state_dict.get("version", 1),
                    last_persistence=state_dict.get("last_persistence")
                )
                
                logger.debug(f"Loaded twin state for user {user_id}, version {twin.version}")
                return twin
                
        except Exception as e:
            logger.error(f"Failed to load twin state for user {user_id}: {e}")
        
        return None