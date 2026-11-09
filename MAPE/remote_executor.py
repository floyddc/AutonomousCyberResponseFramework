import time
from typing import Any, Dict
from knowledge.registry import IncidentRegistry


class RemoteExecutor:
    def __init__(
        self,
        registry: IncidentRegistry,
        *,
        timeout_seconds: float = 45.0,
        poll_interval_seconds: float = 1.0,
    ):
        self.registry = registry
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def execute(self, incident_id: int, action: Dict[str, Any]) -> dict:
        command_id = self.registry.queue_containment_command(incident_id, action)
        deadline = time.monotonic() + self.timeout_seconds

        while time.monotonic() < deadline:
            command = self.registry.get_containment_command(command_id)
            if command is None:
                raise RuntimeError(f"Containment command {command_id} disappeared")
            if command["status"] == "completed":
                result = command.get("result")
                if not isinstance(result, dict):
                    raise RuntimeError("Containment agent returned an invalid result")
                return result
            if command["status"] == "timed_out":
                raise TimeoutError(f"Containment command {command_id} timed out")
            time.sleep(
                min(
                    self.poll_interval_seconds,
                    max(0.0, deadline - time.monotonic()),
                )
            )

        self.registry.timeout_containment_command(command_id)
        raise TimeoutError(
            f"Containment agent did not complete command {command_id} "
            f"within {self.timeout_seconds:g} seconds"
        )
