#!/bin/sh
set -eu

mkdir -p /var/lib/postgresql/data
chown postgres:postgres /var/lib/postgresql/data

exec gosu postgres patroni /etc/patroni.yml
