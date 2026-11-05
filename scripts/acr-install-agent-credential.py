#!/usr/bin/python3
import os
import re
import sys
import tempfile


CREDENTIAL_PATH = "/etc/containment-agent.credential"
CREDENTIAL_PATTERN = re.compile(rb"[0-9a-fA-F]{64}\n?")


def main() -> int:
    if os.geteuid() != 0:
        print("This installer must run as root.", file=sys.stderr)
        return 1
    if len(sys.argv) != 1:
        print("This installer does not accept arguments.", file=sys.stderr)
        return 2

    credential = sys.stdin.buffer.read(66)
    if not CREDENTIAL_PATTERN.fullmatch(credential):
        print("Input must be one 64-character hexadecimal credential.", file=sys.stderr)
        return 2

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".containment-agent.credential.",
        dir="/etc",
    )
    try:
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as credential_file:
            credential_file.write(credential.rstrip(b"\n") + b"\n")
            credential_file.flush()
            os.fsync(credential_file.fileno())
        os.replace(temporary_path, CREDENTIAL_PATH)
        directory_descriptor = os.open("/etc", os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise

    print("Containment-agent credential installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
