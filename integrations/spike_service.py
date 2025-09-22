import os
import time
import secrets
import hmac
import hashlib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from typing import Optional

router = APIRouter(prefix="/api/spike", tags=["spike"])

# Global bus reference
bus: Optional[object] = None

class GenerateSigRequest(BaseModel):
    userId: str = Field(..., min_length=1)

class AuthRequest(BaseModel):
    userId: str = Field(..., min_length=1)

def attach_bus(event_bus) -> None:
    """Attach event bus for publishing events."""
    global bus
    bus = event_bus

@asynccontextmanager
async def lifespan(app):
    """Manage service lifecycle."""
    yield

@router.post("/generate-signature")
async def generate_signature(req: GenerateSigRequest):
    """Generate HMAC signature for Spike API authentication."""
    timestamp = int(time.time())
    signing_secret = os.getenv("SPIKE_SIGNING_SECRET")
    
    if not signing_secret:
        raise HTTPException(status_code=500, detail="SPIKE_SIGNING_SECRET not configured")
    
    # Generate HMAC signature
    message = f"{req.userId}:{timestamp}".encode()
    signature = hmac.new(
        signing_secret.encode(), 
        message, 
        hashlib.sha256
    ).hexdigest()
    
    return {"signature": signature, "timestamp": timestamp}

@router.post("/auth")
async def authenticate(req: AuthRequest):
    """Authenticate with Spike API."""
    # Generate secure token
    token = secrets.token_urlsafe(32)
    
    return {
        "token": token,
        "user_info": {"application_user_id": req.userId}
    }

@router.get("/connected-providers")
async def get_connected_providers():
    """Get list of connected providers."""
    raise HTTPException(status_code=501, detail="Provider connection not yet implemented - configure Spike API credentials")