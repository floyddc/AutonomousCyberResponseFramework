# SETUP VPN Vast.ai VM <-> Local Endpoint VM

- [VPN Config: Linux VM](#vpn-config-linux-vm)
- [VPN Config: Vast.ai VM](#vpn-config-vastai-vm)
- [Agent installation on Linux](#agent-installation-on-linux)
- [Connectivity check: Vast.ai VM](#connectivity-check-vastai-vm)
- [Overall execution](#overall-execution)


## Linux VM endpoint - Preliminar steps
### VPN config
- Install and run Tailscale:
    ```ps
    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up
    ```
- Open the auth link and enable the VPN.
- Generate an auth key (`TS_KEY`) via https://console.tailscale.com/admin/machines (`Settings/Keys`) and take note of it.
- Check connection:
    ```ps
    tailscale status
    tailscale ip -4
    ```
  and take note of the IP address (100.x.y.z) (in my case, **100.82.104.108**).

### SSH setup
- Install OpenSSH-Server and run it:
  ```bash
  sudo apt install openssh-server -y
  sudo systemctl enable sshd
  sudo systemctl start sshd
  ```
- Check if it's active:
  ```bash
  sudo systemctl status ssh
  ```
- Now let's setup the firewall:
  ```ps
  sudo apt install ufw
  sudo systemctl enable ssh
  sudo systemctl start ssh
  sudo ufw enable
  sudo ufw start
  sudo ufw allow 22/tcp
  sudo ufw reload
  sudo ufw status
  ```
- Check if it's listening on port 22: 
  ```ps
  sudo ss -tlnp | grep :22
  ```


## Vast.ai VM - Preliminar steps
_To execute every time you build a new Vast.ai VM._

### VPN config
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
    tailscale up --auth-key="<TS_KEY>" --hostname=acr-vast
    ```
- Check if the service is up and take note of the IP address (`FRAMEWORK_TAILSCALE_IP`):
    ```ps
    tailscale status
    tailscale ip -4
    ```
- Update the `.env` file adding the agent IP address and a custom approval token:
    ```
    AGENT_IP=100.82.104.108
    APPROVAL_TOKEN=<APPROVAL_TOKEN>
    ```

## Linux VM endpoint - Agent installation
Python service that exposes only preset operations (in this moment only `block_ip` is supported), not a remote shell.

- Move on the Linux VM `agent.py`, `firewall.py` and `requirements.txt`, then:
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
  Type: 
  ```text
  AGENT_CREDENTIAL_FILE=/etc/containment-agent.credential
  AGENT_BIND_IP=100.82.104.108
  ACR_PROTECTED_IPS=<FRAMEWORK_TAILSCALE_IP>,100.82.104.108
  ```
  Then close and:
  ```bash
  sudo chmod 0600 /etc/containment-agent.env
  ```


## Vast.ai VM - Final steps
- Check the HTTP connectivity:
  ```ps
  curl --connect-timeout 5 http://100.82.104.108:8787/health
  ```
  The expected reply is:
  ```json
  {"status":"ok","mode":"enforcing","actions":["block_ip"]}
  ```
- Check the SSH connection:
  ```ps
  ssh <LINUX_VM_USER>@100.82.104.108
  ```
- Generate a unique 256-bit SSH credential and install it on the framework host and agent:
  ```bash
  AGENT_IP=100.82.104.108 \
  AGENT_SSH_TARGET=<LINUX_VM_USER>@100.82.104.108 \
    ./scripts/provision_containment_agent_credential.sh
  ```
  The credential is stored locally under `.agent-credentials/` with restrictive permissions and on the agent at `/etc/containment-agent.credential` with owner `root` and mode `0600`. The script reuses the existing credential on subsequent runs. 
  
  > **Restart the framework after provisioning so Docker Compose mounts the credential directory.**


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




## Overall execution
- Build and run the framework, then:
  ```powershell
  curl -X POST http://localhost:8000/alerts -H "Content-Type: application/json" --data-binary "@knowledge/raw_data/edr_alerts/test_alert3.json"
  ```

- If the incident is awaiting approval, inspect the validated choices:
  ```powershell
  curl http://localhost:8000/incidents/<INCIDENT_ID>/approval -H "Authorization: Bearer <APPROVAL_TOKEN>"
  ```

   - Approve **only the index of the `block_ip` action** from that response:

      ```powershell
      curl -X POST http://localhost:8000/incidents/<INCIDENT_ID>/approve -H "Authorization: Bearer <APPROVAL_TOKEN>" -H "Content-Type: application/json" -d "{\"approved_by\":\"diego\",\"action_indexes\":[<BLOCK_IP_ACTION_INDEX>]}"
      ```
      The IP will be blocked on the Linux VM for one hour. Check `GET /incidents/<INCIDENT_ID>` until it reaches `responded` or `failed`, and inspect the agent's systemd journal and `sudo nft list table inet acr` to verify the result.