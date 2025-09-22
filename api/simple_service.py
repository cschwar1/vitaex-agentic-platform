import os
from typing import Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Simple FastAPI app for cloud deployment
app = FastAPI(
    title="VitaeX Agentic Platform",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request models
class ConsentRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    purpose: str = Field(..., description="Purpose of consent")
    scope: str = Field(..., description="Scope of consent")

class SimulationRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    sleep_minutes_delta: int = Field(0, description="Change in sleep minutes")
    activity_minutes_delta: int = Field(0, description="Change in activity minutes")
    stress_reduction: float = Field(0.0, description="Stress reduction factor")
    current_vitality: float = Field(0.6, description="Current vitality score")

# In-memory storage for cloud mode
consent_store = {}
simulation_results = {}

# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/health/ready")
async def readiness_check():
    """Readiness check for cloud deployment."""
    return {
        "status": "ready",
        "agents": ["cloud_protocol_generator", "cloud_vitality_simulator", "cloud_product_curator"],
        "mode": "cloud",
        "message": "Running in cloud mode with simplified agentic features"
    }

# Consent management
@app.post("/consent/grant")
async def grant_consent(request: ConsentRequest):
    """Grant user consent for specific purpose."""
    consent_store[f"{request.user_id}_{request.purpose}"] = {
        "scope": request.scope,
        "granted_at": datetime.utcnow().isoformat()
    }
    return {"status": "granted"}

@app.get("/consent/status")
async def get_consent_status(user_id: str, purpose: str):
    """Get consent status for user."""
    has_consent = f"{user_id}_{purpose}" in consent_store
    return {
        "user_id": user_id,
        "purpose": purpose,
        "consented": has_consent
    }

# Protocol generation (simplified for cloud)
@app.post("/protocol/generate/{user_id}")
async def generate_protocol(user_id: str, context_ref: Optional[str] = None):
    """Generate personalized wellness protocol."""
    # Check consent
    has_consent = f"{user_id}_personalization" in consent_store
    if not has_consent:
        raise HTTPException(status_code=403, detail="Consent required for personalization")
    
    # Generate correlation ID
    correlation_id = f"protocol_{user_id}_{int(datetime.utcnow().timestamp())}"
    
    return {
        "status": "queued",
        "correlation_id": correlation_id,
        "message": "Protocol generation requested. Processing using AI and scientific research.",
        "user_id": user_id
    }

# Vitality simulation
@app.post("/simulation/vitality")
async def simulate_vitality(request: SimulationRequest):
    """Simulate vitality improvements from lifestyle changes."""
    # Simple vitality calculation
    base_vitality = request.current_vitality
    improvement = (
        (request.sleep_minutes_delta / 60.0) * 0.05 +
        (request.activity_minutes_delta / 60.0) * 0.03 +
        request.stress_reduction * 0.07
    )
    new_vitality = min(1.0, max(0.0, base_vitality + improvement))
    
    correlation_id = f"sim_{request.user_id}_{int(datetime.utcnow().timestamp())}"
    
    result = {
        "correlation_id": correlation_id,
        "user_id": request.user_id,
        "baseline_vitality": base_vitality,
        "predicted_vitality": round(new_vitality, 3),
        "improvement": round(improvement, 3),
        "estimated_changes": {
            "energy_boost": round(improvement * 25.0, 1),  # Scale for user understanding
            "recovery_improvement": round(improvement * 15.0, 1)
        },
        "disclaimer": "These are wellness estimates based on research patterns, not medical predictions."
    }
    
    # Store result
    simulation_results[correlation_id] = result
    
    return {
        "status": "completed",
        "correlation_id": correlation_id,
        "results": result
    }

# Product recommendations
@app.post("/products/recommend/{user_id}")
async def request_product_recommendations(user_id: str):
    """Get personalized product recommendations."""
    # Check consent
    has_consent = f"{user_id}_personalization" in consent_store
    if not has_consent:
        raise HTTPException(status_code=403, detail="Consent required for personalization")
    
    # Simple evidence-based recommendations  
    recommendations = [
        {
            "id": "vitamin_d3",
            "name": "Vitamin D3 5000 IU",
            "category": "supplement",
            "rationale": "Supports immune function and bone health based on research evidence",
            "evidence_level": "high",
            "quality_score": 0.9,
            "safety_warnings": ["Consult healthcare provider before use"]
        },
        {
            "id": "omega_3",
            "name": "Omega-3 EPA/DHA",
            "category": "supplement", 
            "rationale": "Supports cardiovascular and brain health with strong research backing",
            "evidence_level": "high",
            "quality_score": 0.85,
            "safety_warnings": ["May interact with blood thinners", "Consult healthcare provider"]
        },
        {
            "id": "magnesium",
            "name": "Magnesium Glycinate",
            "category": "supplement",
            "rationale": "Supports sleep quality and stress management",
            "evidence_level": "moderate",
            "quality_score": 0.8,
            "safety_warnings": ["Start with lower dose", "Consult healthcare provider"]
        }
    ]
    
    correlation_id = f"products_{user_id}_{int(datetime.utcnow().timestamp())}"
    
    return {
        "status": "completed",
        "correlation_id": correlation_id,
        "suggestions": recommendations,
        "disclaimer": "These wellness suggestions are not medical advice. Consult with healthcare professionals before starting supplements."
    }

# Basic practitioner endpoints
@app.get("/reviews")
async def list_reviews():
    """List protocol reviews."""
    return {
        "reviews": [],
        "total": 0,
        "message": "No reviews in cloud mode. Connect to full platform for practitioner features."
    }

if __name__ == "__main__":
    uvicorn.run(
        "api.simple_service:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=False
    )