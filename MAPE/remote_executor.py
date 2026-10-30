import os
import requests


class RemoteExecutor:
    def __init__(self, agent_ip: str):
        if not isinstance(agent_ip, str) or not agent_ip.strip():
            raise ValueError("agent_ip must be a non-empty string")
        self.agent_url = f"http://{agent_ip.strip()}:8787"
        self.token = os.environ.get("AGENT_TOKEN", "")

    def execute(self, action: dict) -> dict:
        if not self.token:
            raise RuntimeError("AGENT_TOKEN is required to execute remote actions")

        response = requests.post(
            f"{self.agent_url}/v1/actions",
            headers={"Authorization": f"Bearer {self.token}"},
            json=action,
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Containment agent returned a non-object response")
        return result
