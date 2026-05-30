import logging

from sward_shared.events.domain_event import DomainEvent

from src.domain.ports.out_.event_publisher_port import EventPublisherPort
from src.infrastructure.config.settings import settings

logger = logging.getLogger(__name__)


class EventBridgeAdapter(EventPublisherPort):
    def publish(self, event: DomainEvent) -> None:
        if settings.environment == "development":
            logger.info("DEV — evento: %s | id=%s", event.event_type, event.event_id)
            return
        from sward_shared.adapters.eventbridge import EventBridgeAdapter as Shared

        Shared(
            event_bus_name=settings.eventbridge_bus_name,
            source="sward-ms-usuarios",
            region=settings.aws_region,
        ).publish(event)
