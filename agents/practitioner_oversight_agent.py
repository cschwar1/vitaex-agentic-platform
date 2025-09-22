from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.privacy.audit import audit_event

JsonDict = Dict[str, Any]


@dataclass
class ReviewRecord:
    protocol_id: str
    user_id: str
    status: str  # draft, awaiting_review, approved, rejected
    reviewers_required: int
    reviewers: List[str] = field(default_factory=list)
    approvals: List[str] = field(default_factory=list)
    rejections: List[str] = field(default_factory=list)
    comments: List[Dict[str, str]] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class PractitionerOversightAgent(BaseAgent):
    def __init__(self, bus):
        super().__init__(AgentConfig(
            name="practitioner_oversight_agent",
            subscribe_topics=["protocol.generated", "protocol.review.requested"]
        ), bus)
        self._reviews: Dict[str, ReviewRecord] = {}

    async def handle(self, event: Event) -> None:
        if event.topic == "protocol.generated":
            pid = f"prot_{event.user_id}_{int(datetime.utcnow().timestamp())}"
            self._reviews[pid] = ReviewRecord(
                protocol_id=pid, user_id=event.user_id or "unknown",
                status="awaiting_review", reviewers_required=2
            )
            audit_event("review.opened", user_id=event.user_id, details={"protocol_id": pid}, correlation_id=event.correlation_id)
            await self._publish_update(pid, "awaiting_review", event.user_id, event.correlation_id)

        elif event.topic == "protocol.review.requested":
            # Payload includes protocol_id, reviewer, action, comment
            payload = event.payload
            pid = payload.get("protocol_id")
            reviewer = payload.get("reviewer")
            action = payload.get("action")  # approve or reject
            comment = payload.get("comment", "")

            rec = self._reviews.get(pid)
            if not rec:
                logger.warning(f"Unknown protocol_id={pid}")
                return

            if reviewer not in rec.reviewers:
                rec.reviewers.append(reviewer)

            if action == "approve" and reviewer not in rec.approvals:
                rec.approvals.append(reviewer)
            if action == "reject" and reviewer not in rec.rejections:
                rec.rejections.append(reviewer)

            if comment:
                rec.comments.append({"reviewer": reviewer, "comment": comment})

            # Consensus logic
            if len(rec.approvals) >= rec.reviewers_required:
                rec.status = "approved"
            elif len(rec.rejections) > 0:
                rec.status = "rejected"
            else:
                rec.status = "awaiting_review"

            rec.updated_at = datetime.utcnow().isoformat()
            self._reviews[pid] = rec
            audit_event("review.updated", user_id=rec.user_id, details={"protocol_id": pid, "status": rec.status}, correlation_id=event.correlation_id)
            await self._publish_update(pid, rec.status, rec.user_id, event.correlation_id)

    async def _publish_update(self, protocol_id: str, status: str, user_id: Optional[str], correlation_id: Optional[str]):
        await self.publish(
            topic="protocol.review.updated",
            event_type="protocol.review.updated",
            payload={"protocol_id": protocol_id, "status": status},
            user_id=user_id,
            correlation_id=correlation_id
        )