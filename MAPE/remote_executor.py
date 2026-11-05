import os
from pathlib import Path
import requests


class RemoteExecutor:
    def __init__(self, agent_ip: str):
        if not isinstance(agent_ip, str) or not agent_ip.strip():
            raise ValueError("agent_ip must be a non-empty string")
        self.agent_url = f"http://{agent_ip.strip()}:8787"
        self.credential_file = Path(
            os.environ.get(
                "AGENT_CREDENTIAL_FILE",
                "/run/acr-agent-credentials/credential",
            )
        )

    def execute(self, action: dict) -> dict:
        try:
            credential = self.credential_file.read_text(encoding="ascii").strip()
        except OSError as exc:
            raise RuntimeError("Unable to read the containment-agent credential") from exc
        if not credential:
            raise RuntimeError("The containment-agent credential is empty")

        response = requests.post(
            f"{self.agent_url}/v1/actions",
            headers={"Authorization": f"Bearer {credential}"},
            json=action,
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Containment agent returned a non-object response")
        return result
