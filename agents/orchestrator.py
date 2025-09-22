import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from loguru import logger

from common.event_bus import EventBus, Event
from agents.base import BaseAgent, AgentConfig

JsonDict = Dict[str, Any]


@dataclass
class OrchestratorConfig:
    name: str = "orchestrator"
    version: str = "1.0.0"
    subscribe_topics: List[str] = None

    def __post_init__(self):
        if self.subscribe_topics is None:
            self.subscribe_topics = [
                "ingest.wearables.standardized",
                "ingest.labs.standardized",
                "knowledge.research.import.completed",
                "simulation.vitality.completed",
                "protocol.review.updated",
            ]


class Orchestrator(BaseAgent):
    def __init__(self, bus: EventBus, config: OrchestratorConfig = OrchestratorConfig()):
        super().__init__(AgentConfig(
            name=config.name,
            version=config.version,
            subscribe_topics=config.subscribe_topics,
        ), bus)
        self._agents: Dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        self._agents[agent.config.name] = agent
        logger.info(f"Registered agent {agent.config.name}")

    async def handle(self, event: Event) -> None:
        logger.info(f"Orchestrator handling event type={event.type} topic={event.topic}")
        if event.topic in ("ingest.wearables.standardized", "ingest.labs.standardized"):
            await self._trigger_twin_update(event)
            await self._trigger_protocol_refresh(event)
        elif event.topic == "knowledge.research.import.completed":
            await self._broadcast_graph_updated(event)
        elif event.topic == "simulation.vitality.completed":
            await self._trigger_protocol_refresh(event)
        elif event.topic == "protocol.review.updated":
            # Optionally notify user or downstream services
            pass

    async def _trigger_twin_update(self, event: Event) -> None:
        await self.bus.publish(
            topic="user.twin.update.requested",
            event_type="twin.update",
            payload={"reason": "new_data", "source_topic": event.topic, "data_meta": event.payload.get("meta", {})},
            user_id=event.user_id,
            correlation_id=event.correlation_id,
        )

    async def _trigger_protocol_refresh(self, event: Event) -> None:
        await self.bus.publish(
            topic="protocol.generate.requested",
            event_type="protocol.request",
            payload={
                "reason": "new_data_or_simulation",
                "source_topic": event.topic,
                "user_context_ref": event.payload.get("user_context_ref"),
            },
            user_id=event.user_id,
            correlation_id=event.correlation_id,
        )

    async def _broadcast_graph_updated(self, event: Event) -> None:
        await self.bus.publish(
            topic="knowledge.graph.updated",
            event_type="graph.updated",
            payload={"graph_version": event.payload.get("graph_version")},
            correlation_id=event.correlation_id,
        )