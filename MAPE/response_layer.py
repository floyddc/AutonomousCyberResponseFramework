import logging
import config
from typing import Any, Dict, List, Optional
from knowledge.registry import IncidentRegistry
from .logging_agent import logging_agent
from MAPE.remote_executor import RemoteExecutor

logger = logging.getLogger(__name__)


class ResponseLayer:
    def __init__(
        self,
        registry: Optional[IncidentRegistry] = None,
        executor: Optional[RemoteExecutor] = None,
    ):
        self.registry = registry or IncidentRegistry()
        self.executor = executor or RemoteExecutor(agent_ip=config.AGENT_IP)

    def _execute_action(
        self, action: Dict[str, Any]
    ) -> Dict[str, Any]:
        action_result = {"action": action, "outcome": "unknown"}

        if action.get("requires_human_approval", False):
            return {**action_result, "outcome": "queued_for_analyst"}

        try:
            remote_result = self.executor.execute(action)

            if (
                isinstance(remote_result, dict)
                and remote_result.get("status") == "ok"
                and remote_result.get("outcome") == "executed"
            ):
                return {
                    **action_result,
                    "outcome": "executed",
                    "remote_result": remote_result,
                }

            return {
                **action_result,
                "outcome": "unconfirmed",
                "remote_result": remote_result,
            }

        except Exception as exc:
            logger.exception("Remote action failed: %s", action.get("type", "unknown"))
            return {
                **action_result,
                "outcome": "failed",
                "error": str(exc),
            }

    def execute(
        self,
        incident_id: int,
        approved_actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        with logging_agent.track("response_layer", "execute", incident_id=incident_id,):

            self.registry.log_action(
                incident_id,
                agent="response_layer",
                action="response_started",
                details={
                    "approved_actions": approved_actions,
                },
            )

            results = [
                self._execute_action(action)
                for action in approved_actions
            ]

            self.registry.log_action(
                incident_id,
                agent="response_layer",
                action="executed_actions",
                details={"results": results},
            )

            return {
                "incident_id": incident_id,
                "results": results,
            }
