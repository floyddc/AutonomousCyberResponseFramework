import json
import config
import logging
import hmac
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Protocol
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class IncidentStore(Protocol):
    def create_incident(
        self,
        source: str,
        customer_id: int,
        summary: str = "",
        description: str = "",
        severity: Optional[str] = None,
        external_id: Optional[str] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> int: ...

    def get_incident(self, incident_id: int) -> Optional[Dict[str, Any]]: ...

    def get_pending_approval(self, incident_id: int) -> Dict[str, Any]: ...

    def approve_pending_actions(
        self,
        incident_id: int,
        approved_by: str,
        action_indexes: list[int],
    ) -> None: ...


def create_server(registry: IncidentStore, host: str, port: int) -> ThreadingHTTPServer:
    class AlertRequestHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, body: Dict[str, Any]) -> None:
            encoded = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _authorize_analyst(self) -> bool:
            approval_token = os.environ.get("APPROVAL_TOKEN", "")
            if not approval_token:
                self._send_json(503, {"error": "Human approval is not configured"})
                return False
            authorization = self.headers.get("Authorization", "")
            if not hmac.compare_digest(authorization, f"Bearer {approval_token}"):
                self._send_json(401, {"error": "Unauthorized"})
                return False
            return True

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send_json(200, {"status": "ok"})
                return

            path = urlsplit(self.path).path
            approval_match = re.fullmatch(
                r"/incidents/([1-9][0-9]*)/approval",
                path,
            )
            if approval_match:
                if not self._authorize_analyst():
                    return
                incident_id = int(approval_match.group(1))
                try:
                    approval = registry.get_pending_approval(incident_id)
                except LookupError:
                    self._send_json(404, {"error": "Incident not found"})
                except ValueError as exc:
                    self._send_json(409, {"error": str(exc)})
                except Exception:
                    logger.exception("Unable to read approval for incident %s", incident_id)
                    self._send_json(500, {"error": "Approval details could not be retrieved"})
                else:
                    self._send_json(200, approval)
                return

            parts = path.strip("/").split("/")
            if len(parts) == 2 and parts[0] == "incidents":
                try:
                    incident_id = int(parts[1])
                    if incident_id <= 0:
                        raise ValueError
                except ValueError:
                    self._send_json(400, {"error": "Incident ID must be a positive integer"})
                    return

                try:
                    incident = registry.get_incident(incident_id)
                except Exception:
                    logger.exception("Unable to retrieve incident %s", incident_id)
                    self._send_json(500, {"error": "Unable to retrieve incident"})
                    return

                if incident is None:
                    self._send_json(404, {"error": "Incident not found"})
                    return

                self._send_json(
                    200,
                    {
                        "incident_id": incident_id,
                        "status": incident["status"],
                        "updated_at": incident.get("updated_at"),
                    },
                )
                return

            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            approval_match = re.fullmatch(r"/incidents/([1-9][0-9]*)/approve", path)
            if approval_match:
                self._approve_incident(int(approval_match.group(1)))
                return
            if path != "/alerts":
                self._send_json(404, {"error": "Not found"})
                return

            content_length = self.headers.get("Content-Length")
            try:
                length = int(content_length) if content_length is not None else -1
            except ValueError:
                self._send_json(400, {"error": "Invalid Content-Length"})
                return

            if length < 0:
                self._send_json(411, {"error": "Content-Length is required"})
                return
            if length > config.MAX_REQUEST_BYTES:
                self._send_json(413, {"error": "Request body is too large"})
                return

            try:
                payload = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(400, {"error": "Request body must be valid JSON"})
                return

            if not isinstance(payload, dict):
                self._send_json(400, {"error": "Alert body must be a JSON object"})
                return

            source = payload.pop("_source", "manual")
            if not isinstance(source, str) or not source.strip():
                self._send_json(400, {"error": "'_source' must be a non-empty string"})
                return

            external_id = payload.pop("external_id", None)
            if external_id is not None and not isinstance(external_id, str):
                self._send_json(400, {"error": "'external_id' must be a string"})
                return

            customer_id = payload.pop("alert_customer_id", None)
            if isinstance(customer_id, bool) or not isinstance(customer_id, int) or customer_id <= 0:
                self._send_json(400, {"error": "'alert_customer_id' must be a positive integer"})
                return

            try:
                incident_id = registry.create_incident(
                    source=source,
                    customer_id=customer_id,
                    raw_payload=payload,
                    external_id=external_id,
                )
                self.send_response(202)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Location", f"/incidents/{incident_id}")
                body = json.dumps(
                    {"incident_id": incident_id, "status": "new"},
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                logger.exception("Unable to accept an alert")
                self._send_json(500, {"error": "Alert could not be accepted"})

        def _approve_incident(self, incident_id: int) -> None:
            if not self._authorize_analyst():
                return

            content_length = self.headers.get("Content-Length")
            try:
                length = int(content_length) if content_length is not None else -1
            except ValueError:
                self._send_json(400, {"error": "Invalid Content-Length"})
                return
            if length < 0:
                self._send_json(411, {"error": "Content-Length is required"})
                return
            if length > config.MAX_REQUEST_BYTES:
                self._send_json(413, {"error": "Request body is too large"})
                return

            try:
                payload = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(400, {"error": "Request body must be valid JSON"})
                return
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "Approval body must be a JSON object"})
                return

            approved_by = payload.get("approved_by")
            if not isinstance(approved_by, str) or not approved_by.strip():
                self._send_json(
                    400,
                    {"error": "'approved_by' must be a non-empty string"},
                )
                return
            action_indexes = payload.get("action_indexes")
            if (
                not isinstance(action_indexes, list)
                or not action_indexes
                or any(
                    isinstance(index, bool)
                    or not isinstance(index, int)
                    or index < 0
                    for index in action_indexes
                )
            ):
                self._send_json(
                    400,
                    {"error": "'action_indexes' must be a non-empty list of indexes"},
                )
                return

            try:
                registry.approve_pending_actions(
                    incident_id,
                    approved_by,
                    action_indexes,
                )
            except LookupError:
                self._send_json(404, {"error": "Incident not found"})
            except ValueError as exc:
                self._send_json(409, {"error": str(exc)})
            except Exception:
                logger.exception("Unable to approve actions for incident %s", incident_id)
                self._send_json(500, {"error": "Approval could not be recorded"})
            else:
                self._send_json(
                    202,
                    {"incident_id": incident_id, "status": "validated"},
                )

        def log_message(self, format: str, *args: Any) -> None:
            logger.info("Alert API %s - %s", self.address_string(), format % args)

    return ThreadingHTTPServer((host, port), AlertRequestHandler)
