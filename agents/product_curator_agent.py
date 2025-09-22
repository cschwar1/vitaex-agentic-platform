from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from loguru import logger

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.privacy.consent import consent_store
from common.privacy.audit import audit_event

@dataclass
class Product:
    """Product representation with comprehensive safety attributes."""
    id: str
    name: str
    category: str
    tags: List[str]
    health_goals: List[str]
    active_ingredients: List[str] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)
    interactions: List[str] = field(default_factory=list)
    allergens: List[str] = field(default_factory=list)
    evidence_level: str = "moderate"
    dosage_info: str = ""
    quality_score: float = 0.7

@dataclass
class UserHealthProfile:
    """User health profile for safety checking."""
    user_id: str
    health_conditions: List[str] = field(default_factory=list)
    medications: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    health_goals: List[str] = field(default_factory=list)
    avoid_ingredients: List[str] = field(default_factory=list)
    source: str = "default"

class ProductCuratorAgent(BaseAgent):
    """Agent for safe, evidence-based product curation with comprehensive safety validation."""
    
    def __init__(self, bus, catalog: Optional[List[Product]] = None):
        super().__init__(AgentConfig(
            name="product_curator_agent",
            subscribe_topics=[
                "product.recommendation.requested",
                "protocol.generated",
                "user.twin.updated"
            ]
        ), bus)
        
        self.catalog = catalog or self._initialize_catalog()
        self.max_recommendations = 5
        self._user_profiles: Dict[str, UserHealthProfile] = {}
        
    def _initialize_catalog(self) -> List[Product]:
        """Initialize evidence-based product catalog with comprehensive safety data."""
        return [
            Product(
                id="supp_vitd3",
                name="Vitamin D3 5000 IU",
                category="supplement",
                tags=["immunity", "bone", "mood"],
                health_goals=["immunity", "bone_health", "mental_wellbeing"], 
                active_ingredients=["cholecalciferol"],
                contraindications=["hypercalcemia", "kidney_disease", "sarcoidosis"],
                interactions=["digoxin", "thiazide_diuretics"],
                evidence_level="high",
                dosage_info="1 capsule daily with food",
                quality_score=0.9
            ),
            Product(
                id="supp_omega3",
                name="Omega-3 (EPA/DHA)",
                category="supplement",
                tags=["cardio", "antiinflammatory", "brain"],
                health_goals=["cardiovascular", "inflammation", "cognitive"],
                active_ingredients=["epa", "dha"], 
                contraindications=["bleeding_disorders", "upcoming_surgery"],
                interactions=["warfarin", "aspirin", "clopidogrel"],
                allergens=["fish"],
                evidence_level="high",
                dosage_info="2 capsules daily with meals",
                quality_score=0.85
            ),
            Product(
                id="supp_mag_glycinate",
                name="Magnesium Glycinate",
                category="supplement",
                tags=["sleep", "relaxation", "muscle"],
                health_goals=["sleep_quality", "stress_reduction", "muscle_recovery"],
                active_ingredients=["magnesium_glycinate"],
                contraindications=["kidney_disease", "heart_block"],
                interactions=["antibiotics", "bisphosphonates"],
                evidence_level="high",
                dosage_info="200-400mg before bed",
                quality_score=0.88
            )
        ]

    async def handle(self, event: Event) -> None:
        """Process events and generate personalized product recommendations with proper safety checks."""
        # Event-specific handling as required
        if event.topic not in self.config.subscribe_topics:
            return
            
        # Resolve user ID from event
        payload = event.payload or {}
        user_id = event.user_id or payload.get("user_id")
        if not user_id:
            logger.warning("No user_id in product curation event")
            return
        
        # Check consent for personalization
        has_consent = consent_store.check(user_id, "personalization")
        
        if event.topic == "product.recommendation.requested":
            await self._handle_recommendation_request(user_id, payload, event.correlation_id, has_consent)
        elif event.topic == "protocol.generated":
            await self._handle_protocol_generated(user_id, payload, event.correlation_id, has_consent) 
        elif event.topic == "user.twin.updated":
            await self._handle_twin_updated(user_id, payload, has_consent)

    async def _handle_recommendation_request(self, user_id: str, payload: Dict[str, Any], 
                                           correlation_id: Optional[str], has_consent: bool) -> None:
        """Handle explicit product recommendation requests."""
        if has_consent:
            profile = self._get_user_profile(user_id, payload)
            recommendations = self._generate_personalized_recommendations(profile)
            safety_checks_performed = True
        else:
            recommendations = self._generate_general_recommendations()
            safety_checks_performed = False
        
        await self.publish(
            topic="product.recommendations",
            event_type="products.curated",
            payload={
                "user_id": user_id,
                "suggestions": recommendations,
                "disclaimer": "These wellness suggestions are not medical advice. Consult with a healthcare professional before starting any new supplement regimen.",
                "personalized": has_consent,
                "safety_validated": safety_checks_performed
            },
            user_id=user_id,
            correlation_id=correlation_id
        )

    async def _handle_protocol_generated(self, user_id: str, payload: Dict[str, Any],
                                       correlation_id: Optional[str], has_consent: bool) -> None:
        """Handle protocol generation events to suggest relevant products."""
        if not has_consent:
            return  # Skip product suggestions if no consent for personalization
            
        # Extract context from generated protocol
        protocol_text = payload.get("protocol", "").lower()
        inferred_goals = []
        
        if "sleep" in protocol_text:
            inferred_goals.append("sleep_quality")
        if "stress" in protocol_text or "cortisol" in protocol_text:
            inferred_goals.append("stress_reduction")
        if "energy" in protocol_text or "fatigue" in protocol_text:
            inferred_goals.append("energy")
        if "immunity" in protocol_text or "immune" in protocol_text:
            inferred_goals.append("immunity")
        
        if inferred_goals:
            # Update user profile with inferred goals
            if user_id not in self._user_profiles:
                self._user_profiles[user_id] = UserHealthProfile(user_id=user_id, source="protocol_inference")
            
            self._user_profiles[user_id].health_goals.extend(inferred_goals)
            
            logger.info(f"Updated user {user_id} profile with goals inferred from protocol: {inferred_goals}")

    async def _handle_twin_updated(self, user_id: str, payload: Dict[str, Any], has_consent: bool) -> None:
        """Handle digital twin updates to refine user health profile."""
        if not has_consent:
            return
            
        # Extract health indicators from twin data
        vitality_score = payload.get("vitality_score", 0.5)
        trends = payload.get("trends", {})
        
        # Update or create user profile based on twin data
        if user_id not in self._user_profiles:
            self._user_profiles[user_id] = UserHealthProfile(user_id=user_id, source="twin_data")
        
        profile = self._user_profiles[user_id]
        
        # Infer health goals from vitality and trends
        if vitality_score < 0.5:
            profile.health_goals = ["energy", "vitality", "recovery"]
        elif trends.get("sleep_efficiency_trend", 0) < -0.1:
            if "sleep_quality" not in profile.health_goals:
                profile.health_goals.append("sleep_quality")
        elif trends.get("stress_score_trend", 0) > 0.1:
            if "stress_reduction" not in profile.health_goals:
                profile.health_goals.append("stress_reduction")
        
        logger.debug(f"Updated user {user_id} health profile from twin data")

    def _get_user_profile(self, user_id: str, payload: Dict[str, Any]) -> UserHealthProfile:
        """Get or create user health profile with safety data."""
        # Check cache first
        if user_id in self._user_profiles:
            return self._user_profiles[user_id]
        
        # Create from event payload if available
        profile = UserHealthProfile(user_id=user_id)
        
        if payload.get("health_profile"):
            health_data = payload["health_profile"]
            profile.health_conditions = health_data.get("conditions", [])
            profile.medications = health_data.get("medications", [])
            profile.allergies = health_data.get("allergies", [])
            profile.health_goals = health_data.get("goals", [])
            profile.avoid_ingredients = health_data.get("avoid_ingredients", [])
            profile.source = "event_payload"
        else:
            # Default to general wellness goals if no specific profile
            profile.health_goals = ["general_wellness"]
            profile.source = "default"
        
        self._user_profiles[user_id] = profile
        return profile

    def _generate_personalized_recommendations(self, profile: UserHealthProfile) -> List[Dict[str, Any]]:
        """Generate personalized recommendations with comprehensive safety validation."""
        recommendations = []
        excluded_count = 0
        
        for product in self.catalog:
            # Comprehensive safety validation
            is_safe, safety_issues = self._validate_product_safety(product, profile)
            
            if not is_safe:
                excluded_count += 1
                logger.info(f"Excluded product {product.name} for user {profile.user_id}: {safety_issues}")
                continue
            
            # Calculate relevance score for safe products
            relevance_score = self._calculate_relevance_score(product, profile)
            
            if relevance_score > 0.3:  # Minimum relevance threshold
                recommendations.append({
                    "id": product.id,
                    "name": product.name,
                    "category": product.category,
                    "score": round(relevance_score, 2),
                    "rationale": self._generate_rationale(product, profile),
                    "health_goals": product.health_goals,
                    "evidence_level": product.evidence_level,
                    "quality_score": product.quality_score,
                    "dosage": product.dosage_info,
                    "safety_warnings": self._generate_safety_warnings(product),
                    "personalized": True
                })
        
        # Sort by relevance score
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        
        # Log safety audit
        audit_event("product.safety_review_completed", user_id=profile.user_id, details={
            "total_products": len(self.catalog),
            "excluded_count": excluded_count,
            "recommended_count": len(recommendations),
            "profile_source": profile.source
        })
        
        return recommendations[:self.max_recommendations]

    def _generate_general_recommendations(self) -> List[Dict[str, Any]]:
        """Generate general wellness recommendations without personalization."""
        # Select high-evidence, low-risk products for general use
        recommended_products = [p for p in self.catalog if p.evidence_level == "high" and not p.contraindications]
        
        recommendations = []
        for product in recommended_products[:3]:
            recommendations.append({
                "id": product.id,
                "name": product.name,
                "category": product.category,
                "rationale": f"General wellness support with {product.evidence_level} evidence",
                "evidence_level": product.evidence_level,
                "quality_score": product.quality_score,
                "safety_warnings": [
                    "Consult healthcare provider before starting any new supplement",
                    f"Read all contraindications: {', '.join(product.contraindications)}" if product.contraindications else ""
                ],
                "personalized": False
            })
        
        return [r for r in recommendations if r]  # Remove empty entries

    def _validate_product_safety(self, product: Product, profile: UserHealthProfile) -> tuple[bool, List[str]]:
        """Perform comprehensive safety validation. Returns (is_safe, list_of_issues)."""
        safety_issues = []
        
        # Check contraindications against user conditions
        if product.contraindications and profile.health_conditions:
            user_conditions = {c.lower().strip() for c in profile.health_conditions}
            contraindications = {c.lower().strip() for c in product.contraindications}
            
            if user_conditions & contraindications:
                safety_issues.append("contraindications")
        
        # Check drug interactions
        if product.interactions and profile.medications:
            user_medications = {m.lower().strip() for m in profile.medications}
            interactions = {i.lower().strip() for i in product.interactions}
            
            if user_medications & interactions:
                safety_issues.append("drug_interactions")
        
        # Check allergies
        if product.allergens and profile.allergies:
            user_allergies = {a.lower().strip() for a in profile.allergies}
            product_allergens = {a.lower().strip() for a in product.allergens}
            
            if user_allergies & product_allergens:
                safety_issues.append("allergies")
        
        # Check avoided ingredients
        if product.active_ingredients and profile.avoid_ingredients:
            ingredients = {i.lower().strip() for i in product.active_ingredients}
            avoided = {a.lower().strip() for a in profile.avoid_ingredients}
            
            if ingredients & avoided:
                safety_issues.append("ingredient_avoidance")
        
        is_safe = len(safety_issues) == 0
        return is_safe, safety_issues

    def _calculate_relevance_score(self, product: Product, profile: UserHealthProfile) -> float:
        """Calculate relevance score based on user goals and evidence."""
        score = 0.0
        
        # Goal alignment (40% of score)
        if profile.health_goals:
            matching_goals = set(product.health_goals) & set(profile.health_goals)
            if matching_goals:
                goal_alignment_score = len(matching_goals) / len(set(profile.health_goals))
                score += 0.4 * goal_alignment_score
        
        # Evidence level (30% of score)
        evidence_scores = {"high": 0.3, "moderate": 0.2, "low": 0.1}
        score += evidence_scores.get(product.evidence_level, 0.1)
        
        # Quality score (30% of score)
        score += 0.3 * product.quality_score
        
        return min(1.0, score)

    def _generate_rationale(self, product: Product, profile: UserHealthProfile) -> str:
        """Generate evidence-based rationale for recommendation."""
        rationale_parts = []
        
        # Goal alignment
        matching_goals = set(product.health_goals) & set(profile.health_goals)
        if matching_goals:
            rationale_parts.append(f"Supports your goals: {', '.join(matching_goals)}")
        
        # Evidence level
        if product.evidence_level == "high":
            rationale_parts.append("Strong scientific evidence")
        elif product.evidence_level == "moderate":
            rationale_parts.append("Moderate research support")
        
        # Quality indicator
        if product.quality_score >= 0.8:
            rationale_parts.append("High quality formulation")
        
        return ". ".join(rationale_parts) if rationale_parts else "General wellness support"

    def _generate_safety_warnings(self, product: Product) -> List[str]:
        """Generate comprehensive safety warnings."""
        warnings = []
        
        if product.contraindications:
            warnings.append(f"Not recommended if you have: {', '.join(product.contraindications)}")
        
        if product.interactions:
            warnings.append(f"May interact with: {', '.join(product.interactions)}")
        
        if product.allergens:
            warnings.append(f"Contains: {', '.join(product.allergens)}")
        
        warnings.append("Consult healthcare provider before starting new supplements")
        
        # Remove any empty warnings
        return [w for w in warnings if w and w.strip()]