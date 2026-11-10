# SETUP VPN Framework Host <-> Endpoint VM

- [Endpoint VM - Preliminary steps](#linux-vm-endpoint---preliminary-steps)
  - [VPN config](#vpn-config)
  - [SSH setup](#ssh-setup)
- [Framework Host - Preliminary step](#vastai-vm---preliminary-steps)
  - [VPN config](#vpn-config-1)
- [Tailscale admin panel - Restrict access](#tailscale-admin-panel---restrict-access)
- [Endpoint VM - Agent installation](#linux-vm-endpoint---agent-installation)
- [Connectivity & SSH credentials](#connectivity--ssh-credentials)
- [Restrict the UFW rules](#restrict-the-ufw-rules)
- [Overall execution](#overall-execution)


## _Endpoint VM_ - Preliminary steps
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
  and take note of the IP address (100.x.y.z) (in my case, **100.126.14.83**).

### SSH setup
- Install OpenSSH-Server and run it:
  ```bash
  sudo apt install openssh-server -y
  sudo systemctl enable ssh
  sudo systemctl start ssh
  ```
- Check if it's active:
  ```bash
  sudo systemctl status ssh
  ```
- Check the current firewall rules before changing them:
  ```ps
  sudo apt install ufw
  sudo ufw enable
  sudo ufw start
  sudo ufw allow 22/tcp
  sudo ufw reload
  sudo ufw status
  ```

  SSH currently listens on all interfaces, and the existing UFW rules allow TCP/22 from anywhere over both IPv4 and IPv6.


## _Framework Host_ - Preliminary steps
_To execute every time you build a new framework host._

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

## _Tailscale admin panel_ - Restrict access
- In the admin console (https://console.tailscale.com/admin/acls/file), add grants so the framework can reach only SSH on the endpoint, and the endpoint can reach the framework API:
    ```json
    "grants": [
      {
        "src": ["<FRAMEWORK_TAILSCALE_IP>/32"],
        "dst": ["100.126.14.83"],
        "ip": ["tcp:22"]
      },
      {
        "src": ["100.126.14.83/32"],
        "dst": ["<FRAMEWORK_TAILSCALE_IP>"],
        "ip": ["tcp:8000"]
      }
    ]
    ```

## _Endpoint VM_ - Agent installation
The endpoint runs a pull agent that opens outbound connections to the framework API.

- Move on the endpoint VM the provided `agent.py` and `firewall.py`, then:
  ```bash
  mkdir containment_agent
  mv agent.py firewall.py containment_agent
  sudo apt update
  sudo apt install -y nftables python3-venv python3-pip
  sudo install -d -m 0750 /opt/containment-agent
  sudo cp -r ~/containment_agent/. /opt/containment-agent/
  sudo python3 -m venv /opt/containment-agent/.venv
  ```

- Create the environment with mode `0600`, owned by root:
  ```bash
  sudo nano /etc/containment-agent.env
  ```
  and type: 
  ```text
  AGENT_CREDENTIAL_FILE=/etc/containment-agent.credential
  FRAMEWORK_URL=http://<FRAMEWORK_TAILSCALE_IP>:8000
  ACR_PROTECTED_IPS=<FRAMEWORK_TAILSCALE_IP>,100.126.14.83
  ```
  Then close and:
  ```bash
  sudo chmod 0600 /etc/containment-agent.env
  ```

> **Every time you need to change the framework IP, modify `/etc/containment-agent.env`**


## Connectivity & SSH credentials
> **Replace `kali` with your `<ENDPOINT_USER>`**

- On the framework, install the credential helper and configure narrowly scoped sudo access. From the framework VM, stage the non-secret helper on the endpoint:
  ```bash
  cd ~/AutonomousCyberResponseFramework
  scp scripts/acr-install-agent-credential.py kali@100.126.14.83:/tmp/acr-install-agent-credential.py
  ssh -t kali@100.126.14.83 'sudo install -o root -g root -m 0755 /tmp/acr-install-agent-credential.py /usr/local/sbin/acr-install-agent-credential && rm -f /tmp/acr-install-agent-credential.py'
  ```

- On the endpoint, create a sudoers rule with `sudo visudo -f /etc/sudoers.d/acr-install-agent-credential` and add this line, replacing `ENDPOINT_USER` with the SSH username:
  ```sudoers
  kali ALL=(root) NOPASSWD: /usr/local/sbin/acr-install-agent-credential ""
  ```
  Then validate the rule:
  ```bash
  sudo chmod 0440 /etc/sudoers.d/acr-install-agent-credential
  sudo visudo -cf /etc/sudoers.d/acr-install-agent-credential
  sudo -l -U kali
  ```
  The helper accepts only a 64-character hexadecimal credential on standard input and writes it atomically to `/etc/containment-agent.credential` with owner `root:root` and mode `0600`. The sudoers entry permits only this helper with no arguments; do not grant passwordless access to a shell, `sudo`, or arbitrary file-install commands.

- Create `/etc/systemd/system/containment-agent.service`:
  ```ini
  [Unit]
  Description=Linux Containment Agent
  After=network-online.target tailscaled.service
  Wants=network-online.target tailscaled.service

  [Service]
  Type=simple
  User=root
  WorkingDirectory=/opt/containment-agent
  EnvironmentFile=/etc/containment-agent.env
  ExecStart=/opt/containment-agent/.venv/bin/python /opt/containment-agent/agent.py
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

- On the framework host, if you don't have a SSH public key (`ls -l ~/.ssh/id_ed25519*`) generate it and transfer it on the endpoint VM:
  ```ps
  ssh-keygen -t ed25519 -a 64 -f ~/.ssh/id_ed25519
  ssh-copy-id -i ~/.ssh/id_ed25519.pub kali@100.126.14.83
  ```

- Then, run ssh-agent and load the private key:
  ```ps
  eval "$(ssh-agent -s)"
  ssh-add ~/.ssh/id_ed25519
  ```

- Check if SSH works without asking the passphrase:
  ```ps
  ssh kali@100.126.14.83
  ```

- In the end, generate a unique 256-bit agent credential and install it on the framework host and endpoint:
    ```bash
    cd ~/AutonomousCyberResponseFramework
    chmod +x scripts/provision_containment_agent_credential.sh
    AGENT_IP=100.126.14.83 \
    AGENT_SSH_TARGET=kali@100.126.14.83
    scripts/provision_containment_agent_credential.sh
    ```
    The credential is stored locally under `.agent-credentials/` with restrictive permissions and on the endpoint at `/etc/containment-agent.credential` with owner `root` and mode `0600`. The script reuses the existing credential on subsequent runs and invokes only the restricted root helper over SSH.

  > **Restart the framework after provisioning so Docker Compose mounts the credential directory.**


## Restrict the UFW rules
- On the framework host, allow the endpoint to reach the API:
  ```bash
  FRAMEWORK_TAILSCALE_IP="<FRAMEWORK_TAILSCALE_IP>"
  AGENT_TAILSCALE_IP="100.126.14.83"
  sudo ufw allow in on tailscale0 proto tcp from "$AGENT_TAILSCALE_IP" to "$FRAMEWORK_TAILSCALE_IP" port 8000
  ```
- On the endpoint, allow SSH from the framework and outbound API polling:
  ```bash
  FRAMEWORK_TAILSCALE_IP="<FRAMEWORK_TAILSCALE_IP>"
  AGENT_TAILSCALE_IP="100.126.14.83"

  sudo ufw allow in on tailscale0 proto tcp from "$FRAMEWORK_TAILSCALE_IP" to "$AGENT_TAILSCALE_IP" port 22
  sudo ufw allow out on tailscale0 proto tcp from "$AGENT_TAILSCALE_IP" to "$FRAMEWORK_TAILSCALE_IP" port 8000
  sudo ufw status numbered
  ```
- Inspect:
  ```bash
  sudo ufw status numbered
  ```
- Delete any old public inbound rules for SSH or the former agent port, replacing `N` with the specific rule number:
  ```bash
  sudo ufw delete N
  sudo ufw status numbered
  ```
- In the end, to apply changes to the active firewall:
  ```bash
  sudo ufw reload
  ```

> **Every time you need to change the framework IP, modify/delete these rules.**

## Overall execution
- Build and run the framework, then:

  - On the endpoint VM, check the HTTP connectivity:
    ```ps
    curl --connect-timeout 5 http://<FRAMEWORK_TAILSCALE_IP>:8000/health
    ```
    The expected reply is `{"status":"ok"}`. 


- On the framework host:
  ```powershell
  curl -X POST http://localhost:8000/alerts -H "Content-Type: application/json" --data-binary "@knowledge/raw_data/edr_alerts/test_alert3.json"
  ```

  - If the incident is awaiting approval, inspect the validated choices:
    ```powershell
    curl http://localhost:8000/incidents/<INCIDENT_ID>/approval -H "Authorization: Bearer approval-test"
    ```

  - Approve **only the index of the `block_ip` action** from that response:

      ```powershell
      curl -X POST http://localhost:8000/incidents/<INCIDENT_ID>/approve -H "Authorization: Bearer approval-test" -H "Content-Type: application/json" -d "{\"approved_by\":\"diego\",\"action_indexes\":[<BLOCK_IP_ACTION_INDEX>]}"
      ```
      The IP will be blocked on the Linux VM for one hour. Check `GET /incidents/<INCIDENT_ID>` until it reaches `responded` or `failed`, and inspect the agent's systemd journal and `sudo nft list table inet acr` to verify the result.