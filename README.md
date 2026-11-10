# Autonomous Cyber-Response Framework

AI Agent-driven framework for ingesting, interpreting, and classifying EDR security events. Orchestration logic allows automated containment execution.

- [Alert example](#alert-example)
- [Environment setup](#setup)
  - [Windows](#windows)
  - [Linux/MacOS](#linuxmacos)
- [Repository and containers setup](#repository-and-containers-setup)
- [Other Terminal](#other-terminal)
  - [Dataset download](#dataset-download)
  - [DB seeding](#db-seeding)
  - [Vector index building](#vector-index-building)
  - [Logs management](#logs-management)
  - [Run the MAPE-K workflow](#run-the-mape-k-workflow)


## Alert example 
```json
{
  "_source": "EDR",
  "external_id": "test-edr-001",
  "alert_customer_id": 1,
  "host": "workstation-042",
  "user": "alice",
  "alert": "Suspicious PowerShell execution with encoded command",
  "command_line": "powershell.exe -EncodedCommand ...",
  "indicators": ["198.51.100.42"],
  "message": "Possible command and control activity"
}
```
Nested fields are possible, but `alert_customer_id` is absolutely required.

## Setup

### Windows
- You need Ollama (https://ollama.com/download/OllamaSetup.exe), Docker and WSL: choose how many resources you want to allocate, typing `notepad "$env:USERPROFILE\.wslconfig"` and paste/modify: 
    ```
    [wsl2]
    memory=<RAM_GB>
    processors=<N_CPU>
    swap=<GB>
    ```
- Then restart the WSL with `wsl --shutdown`.

### Linux/MacOS
You need Docker and Ollama:
```ps
curl -fsSL https://ollama.com/install.sh | sh
```

## Repository and containers setup
- Clone the repo and populate the `.env` file (see `setup_VPN.md` to know where you can get IPs and tokens):
    ```bash
    git clone https://github.com/floyddc/AutonomousCyberResponseFramework.git
    cd AutonomousCyberResponseFramework
    echo "HF_TOKEN=<HF_TOKEN>
    FRAMEWORK_BIND_IP=<FRAMEWORK_TAILSCALE_IP>
    POSTGRES_PASSWORD=<DB_PASSWORD_1>
    POSTGRES_REPLICATION_PASSWORD=<DB_PASSWORD_2>
    APPROVAL_TOKEN=approval-test" > .env
    ```
- Make the script executable:
    ```bash
    mv scripts/setup_VastAi.sh /root
    cd 
    chmod +x setup_VastAi.sh
    ./setup_VastAi.sh
    cd AutonomousCyberResponseFramework
    ```
- And run all:
    ```bash
    docker compose build
    docker compose up
    ```
And wait for the pipeline warmup to complete (see logs with `docker logs python-app`).


## Other Terminal

### Postgres cluster membership
- Check it:
  ```powershell
  cd AutonomousCyberResponseFramework
  docker compose exec postgres-1 patronictl -c /etc/patroni.yml list
  ```

### Dataset download
All files are stored in `knowledge/base/` and divided into different folders.
```powershell
docker exec -it python-app python -m knowledge.fetch_datasets --mitre --telemetry --observables --threatfox-days 2 --sample-size 200
```
`sample-size` is the maximum limit of MITRE procedures to be saved. I suggest 200 just for beginning.


### DB seeding
```powershell
docker exec -it python-app python -m postgres.seed_knowledge_base
```

### Vector index building
The index is stored in `knowledge/indices/`
- **First run:**
  ```powershell
  cd AutonomousCyberResponseFramework
  docker compose run --rm --no-deps python python -m RAG.build_index --reset
  ```
- Then, periodically:
  ```powershell
  cd AutonomousCyberResponseFramework
  docker compose run --rm --no-deps python python -m RAG.build_index
  ```

### Logs management
- **Clean all:**
  ```powershell
  docker exec -it python-app python -m MAPE.logging_agent --clear; truncate -s 0 "$(docker inspect --format='{{.LogPath}}' python-app)"
  ```
- **Print logs of the last run:**
  ```powershell
  docker exec -it python-app python -m MAPE.logging_agent --tail 14; docker logs python-app
  ```

### Run the MAPE-K workflow
```powershell
cd AutonomousCyberResponseFramework
curl -X POST http://localhost:8000/alerts -H "Content-Type: application/json" --data-binary "@knowledge/raw_data/edr_alerts/<ALERT>.json"
```

- If the incident is awaiting approval, inspect the validated choices:
  ```powershell
  curl http://localhost:8000/incidents/<INCIDENT_ID>/approval -H "Authorization: Bearer approval-test"
  ```

- Approve the index of an from the response (_only `block_ip` is supported_):
  ```powershell
  curl -X POST http://localhost:8000/incidents/<INCIDENT_ID>/approve -H "Authorization: Bearer approval-test" -H "Content-Type: application/json" -d "{\"approved_by\":\"diego\",\"action_indexes\":[<BLOCK_IP_ACTION_INDEX>]}"
  ```

## Grafana - to review
- `localhost:3000`
  - Default credentials: `admin / admin`

## Prometheus - to review
- `localhost:9090`