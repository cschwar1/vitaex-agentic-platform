import os
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from loguru import logger
from openai import OpenAI

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.rag.retriever import HybridRetriever
from common.persistence.vector_client import VectorClient
from common.persistence.graph_client import GraphClient
from common.privacy.audit import audit_event
from common.privacy.consent import consent_store

JsonDict = Dict[str, Any]


@dataclass
class ProtocolConfig:
    namespace: str = "knowledge"
    max_references: int = 6


class ProtocolGeneratorAgent(BaseAgent):
    def __init__(self, bus):
        super().__init__(AgentConfig(
            name="protocol_generator_agent",
            subscribe_topics=["protocol.generate.requested"]
        ), bus)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        self.retriever = HybridRetriever(VectorClient(), GraphClient())
        self.protocol_config = ProtocolConfig()

    async def _consent_guard(self, event: Event) -> bool:
        if not event.user_id:
            return True
        return consent_store.check(event.user_id, "personalization")

    async def handle(self, event: Event) -> None:
        user_id = event.user_id or "unknown"
        user_context_ref = event.payload.get("user_context_ref")
        # For demonstration, we simulate embeddings; production uses a real embedding model
        dummy_embedding = [0.01] * 1536
        refs = self.retriever.retrieve(self.protocol_config.namespace, dummy_embedding, graph_node_id=None, k=self.protocol_config.max_references)
        content_refs = "\n".join([f"- {r.get('content')[:200]}" for r in refs])

        prompt = f"""
You are a wellness assistant. Create a daily protocol focused on general wellness (not medical advice).
User context reference: {user_context_ref}
Use the following references:
{content_refs}

Requirements:
- No diagnoses or treatment claims.
- Focus on sleep hygiene, stress reduction, nutrition, movement.
- Include a short rationale and an optional "what-to-track" section.
- Add this exact disclaimer at the end: "This content is for general wellness only and is not medical advice."
"""

        logger.info(f"Generating protocol for user={user_id}")
        resp = self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You produce safe, compliant wellness guidance."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=700
        )
        text = resp.choices[0].message.content

        # Ensure disclaimer
        disclaimer = "This content is for general wellness only and is not medical advice."
        if disclaimer not in text:
            text += f"\n\n{disclaimer}"

        audit_event("protocol.generated", user_id=user_id, details={"length": len(text)}, correlation_id=event.correlation_id)

        await self.publish(
            topic="protocol.generated",
            event_type="protocol.generated",
            payload={"user_id": user_id, "protocol": text},
            user_id=user_id,
            correlation_id=event.correlation_id
        )