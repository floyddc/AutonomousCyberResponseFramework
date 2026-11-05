#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CREDENTIAL_DIR="$PROJECT_ROOT/.agent-credentials/framework"
CREDENTIAL_FILE="$CREDENTIAL_DIR/credential"

if [[ -z "${AGENT_IP:-}" ]]; then
    echo "Set AGENT_IP to the same Tailscale IP configured for the framework." >&2
    exit 1
fi

if [[ -z "${AGENT_SSH_TARGET:-}" ]]; then
    echo "Set AGENT_SSH_TARGET to the verified SSH target, for example user@100.x.y.z." >&2
    exit 1
fi

if [[ ! "$AGENT_SSH_TARGET" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$ ]]; then
    echo "AGENT_SSH_TARGET must have the form user@host." >&2
    exit 1
fi

if [[ "${AGENT_SSH_TARGET#*@}" != "$AGENT_IP" ]]; then
    echo "The SSH target host must match AGENT_IP." >&2
    exit 1
fi

for command_name in flock grep install mktemp mv openssl ssh; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command not found: $command_name" >&2
        exit 1
    fi
done

if [[ -L "$PROJECT_ROOT/.agent-credentials" || -L "$CREDENTIAL_DIR" ]]; then
    echo "Credential paths must not be symbolic links." >&2
    exit 1
fi
install -d -m 0700 "$CREDENTIAL_DIR"
if [[ -L "$CREDENTIAL_FILE" ]]; then
    echo "Credential paths must not be symbolic links." >&2
    exit 1
fi

exec 9>"$CREDENTIAL_DIR/.provision.lock"
flock -x 9

if [[ -e "$CREDENTIAL_FILE" ]]; then
    if [[ ! -f "$CREDENTIAL_FILE" ]] || ! grep -qxE '[[:xdigit:]]{64}' "$CREDENTIAL_FILE"; then
        echo "Existing credential file is invalid; refusing to overwrite it." >&2
        exit 1
    fi
    chmod 0600 "$CREDENTIAL_FILE"
else
    temporary_file="$(mktemp "$CREDENTIAL_DIR/.credential.XXXXXX")"
    trap 'rm -f -- "$temporary_file"' EXIT
    openssl rand -hex 32 >"$temporary_file"
    chmod 0600 "$temporary_file"
    mv "$temporary_file" "$CREDENTIAL_FILE"
    trap - EXIT
fi

ssh \
    -T \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=yes \
    -o ConnectTimeout=10 \
    "$AGENT_SSH_TARGET" \
    'sudo -n sh -c "umask 077; cat > /etc/containment-agent.credential.new && chown root:root /etc/containment-agent.credential.new && chmod 0600 /etc/containment-agent.credential.new && mv -f /etc/containment-agent.credential.new /etc/containment-agent.credential"' \
    <"$CREDENTIAL_FILE"

echo "Containment-agent credential provisioned; its value was not displayed."
