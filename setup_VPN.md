# SETUP VPN Vast.ai VM <-> Local Endpoint VM

- [VPN Config: Linux VM](#vpn-config-linux-vm)
- [VPN Config: Vast.ai VM](#vpn-config-vastai-vm)
- [Agent installation on Linux](#agent-installation-on-linux)
- [Connectivity check: Vast.ai VM](#connectivity-check-vastai-vm)
- [Overall execution](#overall-execution)


## VPN Config: Linux VM
- Install and run Tailscale:
    ```ps
    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up
    ```
- Open the auth link and enable the VPN.
- Generate an auth key (https://console.tailscale.com/admin/machines) (`Settings/Keys`) and take note of it.
- Check connection:
    ```ps
    tailscale status
    tailscale ip -4
    ```
  and take note of the IP address (100.x.y.z).
  
## VPN Config: Vast.ai VM
_To execute every time you build a new VM._
- Check /dev/net/tun on the VM to use Tailscale in traditional mode:
    ```ps
    ls -l /dev/net/tun
    ```
- Install and run Tailscale:
    ```ps
    curl -fsSL https://tailscale.com/install.sh | sh
    mkdir -p /var/lib/tailscale
    tailscaled \
    --tun=tailscale0 \
    --state=/var/lib/tailscale/tailscaled.state &
    ```
- Authenticate the node using the auth key previously generated:
    ```ps
    tailscale up --auth-key="<TSKEY>" --hostname=acr-vast
    ```
- Update the `.env` file adding:
    ```
    AGENT_IP=100.82.104.108
    AGENT_TOKEN=<AGENT_TOKEN>
    APPROVAL_TOKEN=<APPROVAL_TOKEN>
    ```

## Agent installation on Linux
Python service that exposes only preset operations (in this moment only `block_ip` is supported), not a remote shell.

- Move on the Linux VM `agent.py`, `firewall.py`, `requirements.txt` and `.env`, then:
  ```bash
  sudo apt update
  sudo apt install -y nftables python3-venv python3-pip
  sudo install -d -m 0750 /opt/containment-agent
  sudo cp -r ~/containment_agent/. /opt/containment-agent/
  sudo python3 -m venv /opt/containment-agent/.venv
  sudo /opt/containment-agent/.venv/bin/pip install \
    -r /opt/containment-agent/requirements.txt
  ```

- Create `/etc/containment-agent.env` with mode `0600`, owned by root:
  ```bash
  sudo nano /etc/containment-agent.env
  ```
  ```text
  AGENT_TOKEN=<AGENT_TOKEN>
  AGENT_BIND_IP=100.82.104.108
  ACR_PROTECTED_IPS=<FRAMEWORK_TAILSCALE_IP>,100.82.104.108
  ```
  ```bash
  sudo chmod 0600 /etc/containment-agent.env
  ```

> Run the API as a root-owned systemd service because nftables requires `CAP_NET_ADMIN`. Keep it bound to the Tailscale address; do not expose port 8787 to the public network.

- Create `/etc/systemd/system/containment-agent.service`:
  ```ini
  [Unit]
  Description=Linux Containment Agent
  After=network-online.target tailscaled.service
  Wants=network-online.target

  [Service]
  Type=simple
  User=root
  WorkingDirectory=/opt/containment-agent
  EnvironmentFile=/etc/containment-agent.env
  ExecStart=/opt/containment-agent/.venv/bin/uvicorn agent:app --app-dir /opt/containment-agent --host 100.82.104.108 --port 8787
  Restart=on-failure
  NoNewPrivileges=true
  CapabilityBoundingSet=CAP_NET_ADMIN
  AmbientCapabilities=CAP_NET_ADMIN
  ProtectSystem=strict
  ProtectHome=true
  PrivateTmp=true

  [Install]
  WantedBy=multi-user.target
  ```

- Then run:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable --now containment-agent
  sudo systemctl status containment-agent
  ```


## Connectivity check: Vast.ai VM
- Let's suppose the Linux VM IP address is 100.82.104.108:
    ```ps
    curl --connect-timeout 5 http://100.82.104.108:8787/health
    ```
    The expected reply is:
    ```json
    {"status":"ok","mode":"enforcing","actions":["block_ip"]}
    ```

## Overall execution
- Build and run the framework, then:
  ```powershell
  curl -X POST http://localhost:8000/alerts -H "Content-Type: application/json" --data-binary "@knowledge/raw_data/edr_alerts/test_alert3.json"
  ```

- If the incident is awaiting approval, inspect the validated choices:
  ```powershell
  curl http://localhost:8000/incidents/<INCIDENT_ID>/approval -H "Authorization: Bearer <APPROVAL_TOKEN>"
  ```

Approve **only the index of the `block_ip` action** from that response:

```powershell
curl -X POST http://localhost:8000/incidents/<INCIDENT_ID>/approve -H "Authorization: Bearer <APPROVAL_TOKEN>" -H "Content-Type: application/json" -d "{\"approved_by\":\"diego\",\"action_indexes\":[<BLOCK_IP_ACTION_INDEX>]}"
```

The approval endpoint selects actions from the server-stored validated plan; it does not accept a replacement target or modified action. The IP will be blocked on the Linux VM for one hour. Check `GET /incidents/<INCIDENT_ID>` until it reaches `responded` or `failed`, and inspect the agent's systemd journal and `sudo nft list table inet acr` to verify the result.

Before approving, verify that the IP is the intended test IOC and that this VM is an isolated lab host. Do not select `isolate_host` or any other action for this agent; it intentionally rejects actions it does not implement.
