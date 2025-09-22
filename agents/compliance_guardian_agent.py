import re
from typing import Any, Dict, Optional
from dataclasses import dataclass
from loguru import logger

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.privacy.audit import audit_event

JsonDict = Dict[str, Any]


@dataclass
class ComplianceConfig:
    prohibited_patterns: list[str] = None

    def __post_init__(self):
        if self.prohibited_patterns is None:
            self.prohibited_patterns = [
                r"\bdiagnos(e|is|ed)\b",
                r"\btreat(ment|s|ing)?\b",
                r"\bcure(s|d|ing)?\b",
                r"\bprevent\b (?:disease|illness)"
            ]


class ComplianceGuardianAgent(BaseAgent):
    def __init__(self, bus):
        super().__init__(AgentConfig(
            name="compliance_guardian_agent",
            subscribe_topics=["protocol.generated"]
        ), bus)
        self.compliance_config = ComplianceConfig()

    async def handle(self, event: Event) -> None:
        if event.topic == "protocol.generated":
            text = event.payload.get("protocol", "")
            issues = self._scan(text)
            if issues:
                audit_event("compliance.flagged", user_id=event.user_id, details={"issues": issues}, correlation_id=event.correlation_id)
                # Force-append disclaimer and soften language
                fixed = self._soften_language(text)
                await self.publish(
                    topic="protocol.generated",
                    event_type="protocol.generated.sanitized",
                    payload={"user_id": event.user_id, "protocol": fixed},
                    user_id=event.user_id,
                    correlation_id=event.correlation_id
                )

    def _scan(self, text: str) -> list[str]:
        hits = []
        for pat in self.compliance_config.prohibited_patterns:
            if re.search(pat, text, flags=re.IGNORECASE):
                hits.append(pat)
        if "not medical advice" not in text.lower():
            hits.append("missing_disclaimer")
        return hits

    def _soften_language(self, text: str) -> str:
        text = re.sub(r"\b(treat|cure|prevent)\b", "may support", text, flags=re.IGNORECASE)
        disclaimer = "This content is for general wellness only and is not medical advice."
        if disclaimer.lower() not in text.lower():
            text += f"\n\n{disclaimer}"
        return text