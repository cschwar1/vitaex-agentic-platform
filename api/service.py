import asyncio
import os
from typing import Any, Dict, Optional, List
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from common.event_bus import EventBus
from agents.orchestrator import Orchestrator
from agents.data_ingestion_agent import DataIngestionAgent
from agents.knowledge_graph_agent import KnowledgeGraphAgent
from agents.digital_twin_agent import DigitalTwinAgent
from agents.vitality_simulation_agent import VitalitySimulationAgent
from agents.protocol_generator_agent import ProtocolGeneratorAgent
from agents.practitioner_oversight_agent import PractitionerOversightAgent
from agents.compliance_guardian_agent import ComplianceGuardianAgent
from agents.product_curator_agent import ProductCuratorAgent
from integrations.spike_service import router as spike_router, attach_bus as attach_spike_bus, lifespan as spike_lifespan
from integrations.omnos_connector import OmnosConnector
from integrations.questionnaire_processor import QuestionnaireProcessor
from common.privacy.consent import consent_store
from common.privacy.audit import audit_event

JsonDict = Dict[str, Any]


# Request/Response models
class ConsentRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    purpose: str = Field(..., description="Purpose of consent")
    scope: str = Field(..., description="Scope of consent")
    expires_at: Optional[str] = Field(None, description="Optional expiration date")


class SimulationRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    sleep_minutes_delta: int = Field(0, description="Change in sleep minutes")
    activity_minutes_delta: int = Field(0, description="Change in activity minutes")
    stress_reduction: float = Field(0.0, ge=0.0, le=1.0, description="Stress reduction factor")
    current_vitality: float = Field(0.6, ge=0.0, le=1.0, description="Current vitality score")


class ReviewDecision(BaseModel):
    reviewer: str = Field(..., description="Reviewer identifier")
    action: str = Field(..., description="Action: approve or reject")
    comment: Optional[str] = Field(None, description="Optional review comment")


class QuestionnaireSubmission(BaseModel):
    user_id: str = Field(..., description="User ID")
    questionnaire_id: str = Field(..., description="Questionnaire identifier")
    answers: List[JsonDict] = Field(..., description="Answer items")


# Global instances
bus: Optional[EventBus] = None
orchestrator: Optional[Orchestrator] = None
agents: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global bus, orchestrator, agents
    
    # Initialize EventBus
    bus = EventBus(bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS"))
    await bus.start()
    
    # Initialize agents
    orchestrator = Orchestrator(bus)
    agents = {
        "data_ingestion": DataIngestionAgent(bus),
        "knowledge_graph": KnowledgeGraphAgent(bus),
        "digital_twin": DigitalTwinAgent(bus),
        "vitality_simulation": VitalitySimulationAgent(bus),
        "protocol_generator": ProtocolGeneratorAgent(bus),
        "practitioner_oversight": PractitionerOversightAgent(bus),
        "compliance_guardian": ComplianceGuardianAgent(bus),
        "product_curator": ProductCuratorAgent(bus)
    }
    
    # Start all agents
    await asyncio.gather(
        orchestrator.start(),
        *[agent.start() for agent in agents.values()]
    )
    
    # Register agents with orchestrator
    for agent in agents.values():
        orchestrator.register_agent(agent)
    
    # Attach bus to integrations
    attach_spike_bus(bus)
    
    # Initialize HTTP client for Spike service
    async with spike_lifespan(app):
        logger.info("Agentic platform started")
        yield
    
    # Shutdown
    await bus.stop()
    logger.info("Agentic platform stopped")


# Create FastAPI app
app = FastAPI(
    title="VitaeX Agentic Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Observability
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

# Include routers
app.include_router(spike_router)


# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/ready")
async def readiness_check():
    """Readiness check verifying agent status."""
    global orchestrator, agents
    
    if not orchestrator or not agents:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    # Check if key agents are running
    ready_agents = []
    for name, agent in agents.items():
        if agent._running:
            ready_agents.append(name)
    
    if len(ready_agents) < len(agents):
        return {
            "status": "partial",
            "ready_agents": ready_agents,
            "total_agents": len(agents)
        }
    
    return {
        "status": "ready",
        "agents": ready_agents
    }


@app.get("/health/live")
async def liveness_check():
    """Liveness check."""
    return {"status": "alive"}


# Orchestrator endpoints
@app.post("/orchestrator/research/import")
async def request_research_import():
    """Trigger research import from configured sources."""
    if not bus:
        raise HTTPException(status_code=503, detail="Event bus not available")
    
    correlation_id = await bus.publish(
        topic="knowledge.research.import.requested",
        event_type="research.import.request",
        payload={}
    )
    return {"status": "queued", "correlation_id": correlation_id}


# Consent management endpoints
@app.post("/consent/grant")
async def grant_consent(request: ConsentRequest):
    """Grant user consent for specific purpose."""
    consent_store.grant(
        user_id=request.user_id,
        purpose=request.purpose,
        scope=request.scope,
        expires_at=request.expires_at
    )
    audit_event(
        "consent.grant",
        user_id=request.user_id,
        details={"purpose": request.purpose, "scope": request.scope}
    )
    return {"status": "granted"}


@app.post("/consent/revoke")
async def revoke_consent(user_id: str, purpose: str):
    """Revoke user consent for specific purpose."""
    consent_store.revoke(user_id, purpose)
    audit_event(
        "consent.revoke",
        user_id=user_id,
        details={"purpose": purpose}
    )
    return {"status": "revoked"}


@app.get("/consent/status")
async def get_consent_status(user_id: str, purpose: Optional[str] = None):
    """Get consent status for user."""
    if purpose:
        return {
            "user_id": user_id,
            "purpose": purpose,
            "consented": consent_store.check(user_id, purpose)
        }
    
    # Return all consents for user (would need store enhancement)
    return {
        "user_id": user_id,
        "message": "Full consent list requires database implementation"
    }


# Simulation endpoints
@app.post("/simulation/vitality")
async def simulate_vitality(request: SimulationRequest):
    """Request vitality simulation for what-if scenarios."""
    if not bus:
        raise HTTPException(status_code=503, detail="Event bus not available")
    
    correlation_id = await bus.publish(
        topic="simulation.vitality.requested",
        event_type="simulation.request",
        payload={
            "sleep_minutes_delta": request.sleep_minutes_delta,
            "activity_minutes_delta": request.activity_minutes_delta,
            "stress_reduction": request.stress_reduction,
            "current_vitality": request.current_vitality,
        },
        user_id=request.user_id
    )
    return {"status": "queued", "correlation_id": correlation_id}


# Data sync endpoints
@app.post("/omnos/sync/{user_id}")
async def sync_omnos(user_id: str):
    """Sync Omnos lab data for user."""
    if not bus:
        raise HTTPException(status_code=503, detail="Event bus not available")
    
    connector = OmnosConnector(bus=bus)
    count = await connector.standardize_and_publish(user_id)
    return {"status": "synced", "count": count}


@app.post("/questionnaire/submit")
async def submit_questionnaire(submission: QuestionnaireSubmission):
    """Submit questionnaire responses."""
    if not bus:
        raise HTTPException(status_code=503, detail="Event bus not available")
    
    processor = QuestionnaireProcessor(bus)
    result = await processor.process(
        user_id=submission.user_id,
        questionnaire_id=submission.questionnaire_id,
        answers=submission.answers
    )
    return result


# Practitioner review endpoints
@app.get("/reviews")
async def list_reviews(
    status: Optional[str] = Query(None, description="Filter by status"),
    reviewer: Optional[str] = Query(None, description="Filter by reviewer"),
    limit: int = Query(50, ge=1, le=100)
):
    """List protocol reviews with optional filters."""
    global agents
    
    if "practitioner_oversight" not in agents:
        raise HTTPException(status_code=503, detail="Practitioner oversight not available")
    
    oversight_agent = agents["practitioner_oversight"]
    all_reviews = oversight_agent._reviews.values()
    
    # Apply filters
    filtered = all_reviews
    if status:
        filtered = [r for r in filtered if r.status == status]
    if reviewer:
        filtered = [r for r in filtered if reviewer in r.reviewers]
    
    # Convert to response format
    reviews = []
    for review in list(filtered)[:limit]:
        reviews.append({
            "protocol_id": review.protocol_id,
            "user_id": review.user_id,
            "status": review.status,
            "reviewers_required": review.reviewers_required,
            "reviewers": review.reviewers,
            "approvals": len(review.approvals),
            "rejections": len(review.rejections),
            "updated_at": review.updated_at
        })
    
    return {
        "reviews": reviews,
        "total": len(filtered),
        "limit": limit
    }


@app.get("/reviews/{protocol_id}")
async def get_review(protocol_id: str):
    """Get specific protocol review details."""
    global agents
    
    if "practitioner_oversight" not in agents:
        raise HTTPException(status_code=503, detail="Practitioner oversight not available")
    
    oversight_agent = agents["practitioner_oversight"]
    review = oversight_agent._reviews.get(protocol_id)
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return {
        "protocol_id": review.protocol_id,
        "user_id": review.user_id,
        "status": review.status,
        "reviewers_required": review.reviewers_required,
        "reviewers": review.reviewers,
        "approvals": review.approvals,
        "rejections": review.rejections,
        "comments": review.comments,
        "updated_at": review.updated_at
    }


@app.post("/reviews/{protocol_id}/decision")
async def submit_review_decision(protocol_id: str, decision: ReviewDecision):
    """Submit review decision for a protocol."""
    global bus
    
    if not bus:
        raise HTTPException(status_code=503, detail="Event bus not available")
    
    # Validate action
    if decision.action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    
    # Publish review decision
    correlation_id = await bus.publish(
        topic="protocol.review.requested",
        event_type="review.decision",
        payload={
            "protocol_id": protocol_id,
            "reviewer": decision.reviewer,
            "action": decision.action,
            "comment": decision.comment
        }
    )
    
    audit_event(
        "review.decision",
        user_id=decision.reviewer,
        details={
            "protocol_id": protocol_id,
            "action": decision.action
        },
        correlation_id=correlation_id
    )
    
    return {
        "status": "submitted",
        "correlation_id": correlation_id
    }


# WebSocket for real-time collaboration
connected_peers: Dict[str, List[WebSocket]] = {}


@app.websocket("/ws/collab/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    """WebSocket endpoint for real-time practitioner collaboration."""
    await websocket.accept()
    
    # Add to room
    if room_id not in connected_peers:
        connected_peers[room_id] = []
    connected_peers[room_id].append(websocket)
    
    # Notify others in room
    for peer in connected_peers[room_id]:
        if peer != websocket:
            try:
                await peer.send_json({
                    "type": "user_joined",
                    "timestamp": datetime.utcnow().isoformat()
                })
            except:
                pass
    
    try:
        while True:
            data = await websocket.receive_text()
            # Broadcast to all peers in the room
            for peer in connected_peers[room_id]:
                if peer != websocket:
                    try:
                        await peer.send_text(data)
                    except:
                        pass
    except WebSocketDisconnect:
        # Remove from room
        connected_peers[room_id].remove(websocket)
        
        # Notify others
        for peer in connected_peers[room_id]:
            try:
                await peer.send_json({
                    "type": "user_left",
                    "timestamp": datetime.utcnow().isoformat()
                })
            except:
                pass
        
        # Clean up empty rooms
        if not connected_peers[room_id]:
            del connected_peers[room_id]


# Product recommendation endpoint
@app.post("/products/recommend/{user_id}")
async def request_product_recommendations(user_id: str):
    """Request personalized product recommendations."""
    if not bus:
        raise HTTPException(status_code=503, detail="Event bus not available")
    
    correlation_id = await bus.publish(
        topic="product.recommendation.requested",
        event_type="recommendation.request",
        payload={"user_id": user_id},
        user_id=user_id
    )
    
    return {"status": "queued", "correlation_id": correlation_id}


# Protocol generation endpoint
@app.post("/protocol/generate/{user_id}")
async def generate_protocol(user_id: str, context_ref: Optional[str] = None):
    """Request protocol generation for user."""
    if not bus:
        raise HTTPException(status_code=503, detail="Event bus not available")
    
    correlation_id = await bus.publish(
        topic="protocol.generate.requested",
        event_type="protocol.request",
        payload={
            "user_id": user_id,
            "user_context_ref": context_ref
        },
        user_id=user_id
    )
    
    return {"status": "queued", "correlation_id": correlation_id}


if __name__ == "__main__":
    uvicorn.run(
        "api.service:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=True
    )