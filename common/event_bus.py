import asyncio
import json
import os
import signal
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, List

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from loguru import logger

JsonDict = Dict[str, Any]
EventHandler = Callable[[JsonDict], Awaitable[None]]

@dataclass
class Event:
    topic: str
    type: str
    payload: JsonDict
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    timestamp: str = datetime.now(timezone.utc).isoformat()

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self), separators=(",", ":"), default=str).encode("utf-8")

    @staticmethod
    def from_bytes(data: bytes) -> "Event":
        obj = json.loads(data.decode("utf-8"))
        return Event(**obj)


class EventBus:
    def __init__(self, bootstrap_servers: Optional[str] = None, consumer_group: str = "vitaex-agents"):
        self.bootstrap_servers = bootstrap_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.consumer_group = consumer_group
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumers: List[AIOKafkaConsumer] = []
        self._run = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        logger.info("Starting EventBus", bootstrap=self.bootstrap_servers)
        self._producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers, value_serializer=lambda v: v)
        await self._producer.start()
        self._run = True
        self._register_signals()

    def _register_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Not supported on Windows
                pass

    async def stop(self) -> None:
        if not self._run:
            return
        self._run = False
        logger.info("Stopping EventBus")
        try:
            for consumer in self._consumers:
                await consumer.stop()
        finally:
            self._consumers.clear()
            if self._producer:
                await self._producer.stop()
            self._stop_event.set()

    async def publish(self, topic: str, event_type: str, payload: JsonDict, user_id: Optional[str] = None,
                      correlation_id: Optional[str] = None) -> str:
        if not self._producer:
            raise RuntimeError("Producer not started")
        corr = correlation_id or str(uuid.uuid4())
        event = Event(topic=topic, type=event_type, payload=payload, user_id=user_id, correlation_id=corr)
        await self._producer.send_and_wait(topic, event.to_bytes())
        logger.debug(f"Published event {event.type} to {topic} correlation_id={corr}")
        return corr

    async def subscribe(self, topic: str, handler: EventHandler, pattern: bool = False) -> None:
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.consumer_group,
            value_deserializer=lambda v: v,
            enable_auto_commit=True,
            auto_offset_reset="latest",
        )
        await consumer.start()
        self._consumers.append(consumer)
        asyncio.create_task(self._consume_loop(consumer, handler, topic))

    async def _consume_loop(self, consumer: AIOKafkaConsumer, handler: EventHandler, topic: str) -> None:
        logger.info(f"Consuming topic={topic} group={self.consumer_group}")
        async for msg in consumer:
            try:
                evt = Event.from_bytes(msg.value)
                await handler(asdict(evt))
            except Exception as e:
                logger.exception(f"Error handling message on topic={topic}: {e}")

    async def wait_until_stopped(self) -> None:
        await self._stop_event.wait()


# Recommended Kafka topics for this platform (create them externally or via IaC):
# - ingest.wearables.raw
# - ingest.wearables.standardized
# - ingest.labs.raw
# - ingest.labs.standardized
# - knowledge.research.import.requested
# - knowledge.research.import.completed
# - knowledge.graph.updated
# - user.twin.updated
# - simulation.vitality.completed
# - protocol.generated
# - protocol.review.requested
# - protocol.review.updated
# - compliance.alert