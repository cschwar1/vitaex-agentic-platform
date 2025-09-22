import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable

from loguru import logger

from common.event_bus import EventBus, Event

JsonDict = Dict[str, Any]


@dataclass
class AgentConfig:
    name: str
    version: str = "1.0.0"
    description: Optional[str] = None
    subscribe_topics: list[str] = field(default_factory=list)
    publish_topic: Optional[str] = None


class BaseAgent:
    def __init__(self, config: AgentConfig, bus: EventBus):
        self.config = config
        self.bus = bus
        self._running = False
        self._state: Dict[str, Any] = {}
        self._ready_event = asyncio.Event()

    async def start(self) -> None:
        logger.info(f"Starting agent {self.config.name} v{self.config.version}")
        for topic in self.config.subscribe_topics:
            await self.bus.subscribe(topic, self._handle_event)
        self._running = True
        self._ready_event.set()

    async def stop(self) -> None:
        logger.info(f"Stopping agent {self.config.name}")
        self._running = False

    async def ready(self) -> None:
        await self._ready_event.wait()

    async def _handle_event(self, event_dict: JsonDict) -> None:
        try:
            event = Event(**event_dict)
            logger.debug(f"{self.config.name} received event type={event.type} topic={event.topic}")
            if not await self._consent_guard(event):
                logger.warning(f"{self.config.name} consent guard blocked event correlation_id={event.correlation_id}")
                return
            await self.handle(event)
        except Exception as e:
            logger.exception(f"Agent {self.config.name} error: {e}")
            await self.on_error(e, event_dict)

    async def handle(self, event: Event) -> None:
        raise NotImplementedError

    async def on_error(self, error: Exception, event_dict: Optional[JsonDict] = None) -> None:
        # Default: just log; override to route to DLQ or compliance alert
        logger.error(f"Error in {self.config.name}: {error}")

    async def publish(self, topic: str, event_type: str, payload: JsonDict, user_id: Optional[str] = None,
                      correlation_id: Optional[str] = None) -> str:
        return await self.bus.publish(topic, event_type, payload, user_id, correlation_id)

    def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    async def _consent_guard(self, event: Event) -> bool:
        # Overridden by agents that must enforce consent on inbound events.
        # Default to True to allow through.
        return True