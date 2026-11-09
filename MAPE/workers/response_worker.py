import logging
from typing import Optional
from MAPE.response_layer import ResponseLayer
from MQTT.events import Event
from MQTT.topics import ACTION_VALIDATED, RESPONSE_GROUP
from MQTT.worker import Worker
from knowledge.registry import (
    IncidentRegistry,
    STATUS_FAILED,
    STATUS_RESPONDED,
    STATUS_RESPONSE,
)

logger = logging.getLogger(__name__)


class ResponseWorker(Worker):
    def __init__(
        self,
        *,
        worker_name: str = "response-worker",
        registry: Optional[IncidentRegistry] = None,
        response_layer: Optional[ResponseLayer] = None,
    ):
        shared_registry = registry or IncidentRegistry()
        super().__init__(
            worker_name=worker_name,
            input_topic=ACTION_VALIDATED,
            group=RESPONSE_GROUP,
            registry=shared_registry,
        )
        self.response_layer = response_layer or ResponseLayer(registry=self.registry)


    # BUSINESS LOGIC ----------------------------------------------------------------------------------------------------------------------------------------------------------
    def handle_event(self, event: Event) -> None:

        # collect approved actions from the event payload
        actions = event.payload.get("approved_actions")
        if not isinstance(actions, list) or not actions:
            raise RuntimeError("Validated event has no approved actions")
        if any(
            not isinstance(action, dict)
            or action.get("requires_human_approval", False)
            for action in actions
        ):
            self.transition_incident(
                incident_id=event.incident_id,
                status=STATUS_FAILED,
                payload={"error": "Response received an action without approval"},
                correlation_id=event.correlation_id,
            )
            return

        self.transition_incident(
            incident_id=event.incident_id,
            status=STATUS_RESPONSE,
            payload={"approved_actions": actions},
            correlation_id=event.correlation_id,
        )

        # execute the approved actions using the response layer
        response = self.response_layer.execute(event.incident_id, actions)
        results = response.get("results")
        succeeded = (
            isinstance(results, list)
            and bool(results)
            and all(
                isinstance(result, dict) and result.get("outcome") == "executed"
                for result in results
            )
        )
        status = STATUS_RESPONDED if succeeded else STATUS_FAILED

        # send the final status of the incident
        self.transition_incident(
            incident_id=event.incident_id,
            status=status,
            payload={"response": response},
            correlation_id=event.correlation_id,
            idempotency_key=f"response:{event.event_id}:{status}",
        )
