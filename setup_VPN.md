# SETUP VPN Vast.ai VM <-> Local Endpoint VM

- [Linux VM endpoint - Preliminary steps](#linux-vm-endpoint---preliminary-steps)
  - [VPN config](#vpn-config)
  - [SSH setup](#ssh-setup)
- [Vast.ai VM - Preliminary step](#vastai-vm---preliminary-steps)
  - [VPN config](#vpn-config-1)
- [Linux VM endpoint - Agent installation](#linux-vm-endpoint---agent-installation)
- [Vast.ai VM - Connectivity & SSH credentials](#vastai-vm---connectivity--ssh-credentials)
- [Tailscale admin panel - Restrict access](#tailscale-admin-panel---restrict-access)
- [Linux VM endpoint - Restrict the UFW rules](#linux-vm-endpoint---restrict-the-ufw-rules)
- [Overall execution](#overall-execution)


## _Linux VM endpoint_ - Preliminary steps
_To execute at the first usage._

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
- Check the current firewall rules before changing them:
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

  SSH currently listens on all interfaces, and the existing UFW rules allow TCP/22 from anywhere over both IPv4 and IPv6.


## _Vast.ai VM_ - Preliminary steps
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

## _Linux VM endpoint_ - Agent installation
Python service that exposes only preset operations (in this moment only `block_ip` is supported), not a remote shell.

- Create a `containment_agent` directory and `agent.py`, `firewall.py`, `requirements.txt`, then:
  ```bash
  mv agent.py firewall.py requirements.txt containment_agent
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

- Install the credential helper and configure narrowly scoped sudo access. From the framework VM, stage the non-secret helper on the endpoint:
  ```bash
  cd ~/AutonomousCyberResponseFramework
  scp scripts/acr-install-agent-credential.py \
    <LINUX_VM_USER>@100.82.104.108:/tmp/acr-install-agent-credential.py
  ssh -t <LINUX_VM_USER>@100.82.104.108 \
    'sudo install -o root -g root -m 0755 /tmp/acr-install-agent-credential.py /usr/local/sbin/acr-install-agent-credential && rm -f /tmp/acr-install-agent-credential.py'
  ```
  On the endpoint, create a sudoers rule with `sudo visudo -f /etc/sudoers.d/acr-install-agent-credential` and add this line, replacing `LINUX_VM_USER` with the SSH username:
  ```sudoers
  LINUX_VM_USER ALL=(root) NOPASSWD: /usr/local/sbin/acr-install-agent-credential ""
  ```
  Then validate the rule:
  ```bash
  sudo chmod 0440 /etc/sudoers.d/acr-install-agent-credential
  sudo visudo -cf /etc/sudoers.d/acr-install-agent-credential
  sudo -l -U <LINUX_VM_USER>
  ```
  The helper accepts only a 64-character hexadecimal credential on standard input and writes it atomically to `/etc/containment-agent.credential` with owner `root:root` and mode `0600`. The sudoers entry permits only this helper with no arguments; do not grant passwordless access to a shell, `sudo`, or arbitrary file-install commands.

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


## _Vast.ai VM_ - Connectivity & SSH credentials
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
- If you don't have a SSH public key (`ls -l ~/.ssh/id_ed25519*`):
  ```ps
  ssh-keygen -t ed25519 -a 64 -f ~/.ssh/id_ed25519
  ssh-copy-id -i ~/.ssh/id_ed25519.pub kali@100.82.104.108
  ```
- Generate a unique 256-bit agent credential and install it on the framework host and endpoint:
  ```bash
  cd ~/AutonomousCyberResponseFramework
  chmod +x scripts/provision_containment_agent_credential.sh
  AGENT_IP=100.82.104.108 \
  AGENT_SSH_TARGET=<LINUX_VM_USER>@100.82.104.108 \
    scripts/provision_containment_agent_credential.sh
  ```
  The credential is stored locally under `.agent-credentials/` with restrictive permissions and on the endpoint at `/etc/containment-agent.credential` with owner `root` and mode `0600`. The script reuses the existing credential on subsequent runs and invokes only the restricted root helper over SSH.

  > **Restart the framework after provisioning so Docker Compose mounts the credential directory.**


## _Tailscale admin panel_ - Restrict access
- In the admin console (https://console.tailscale.com/admin/acls/file), add a grant to the existing policy for the framework node to reach only SSH and the containment API on this endpoint:
    ```json
    "grants": [
      {
        "src": ["<FRAMEWORK_TAILSCALE_IP>/32"],
        "dst": ["100.82.104.108"],
        "ip": ["tcp:22", "tcp:8787"]
      }
    ]
    ```

## _Linux VM endpoint_ - Restrict the UFW rules
- Allow TCP connections from the framework:
  ```bash
  FRAMEWORK_TAILSCALE_IP="<FRAMEWORK_TAILSCALE_IP>"
  AGENT_TAILSCALE_IP="100.82.104.108"

  sudo ufw allow in on tailscale0 proto tcp from "$FRAMEWORK_TAILSCALE_IP" to "$AGENT_TAILSCALE_IP" port 22
  sudo ufw allow in on tailscale0 proto tcp from "$FRAMEWORK_TAILSCALE_IP" to "$AGENT_TAILSCALE_IP" port 8787
  sudo ufw status numbered
  ```
- Inspect:
  ```bash
  sudo ufw status numbered
  ```
- And delete only the old `22/tcp ALLOW IN Anywhere` and `22/tcp (v6) ALLOW IN Anywhere (v6)` entries, replacing the `N` (rule number):
  ```bash
  sudo ufw delete N
  sudo ufw status numbered
  ```
- In the end, to apply changes to the active firewall:
  ```bash
  sudo ufw reload
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