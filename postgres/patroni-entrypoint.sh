#!/bin/sh
set -eu

mkdir -p /var/lib/postgresql/data
chown postgres:postgres /var/lib/postgresql/data

umask 077
/opt/patroni/bin/python - <<'PY'
import os
import yaml

with open("/etc/patroni.yml", encoding="utf-8") as config_file:
    config = yaml.safe_load(config_file)

if not isinstance(config, dict):
    raise SystemExit("Patroni configuration must be a YAML object")

passwords = {
    "superuser": os.environ.get("POSTGRES_PASSWORD"),
    "replication": os.environ.get("POSTGRES_REPLICATION_PASSWORD"),
}
if any(not password for password in passwords.values()):
    raise SystemExit("PostgreSQL superuser and replication passwords must be set")

config.setdefault("postgresql", {})["authentication"] = {
    "superuser": {
        "username": "cyberresponse",
        "password": passwords["superuser"],
    },
    "replication": {
        "username": "replicator",
        "password": passwords["replication"],
    },
}

with open("/tmp/patroni.yml", "w", encoding="utf-8") as config_file:
    yaml.safe_dump(config, config_file, sort_keys=False)
PY
chown postgres:postgres /tmp/patroni.yml
chmod 0600 /tmp/patroni.yml

exec gosu postgres patroni /tmp/patroni.yml
