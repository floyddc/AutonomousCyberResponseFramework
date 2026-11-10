FROM postgres:15

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && python3 -m venv /opt/patroni \
    && /opt/patroni/bin/pip install --no-cache-dir \
        "patroni[etcd3]==4.0.6" \
        "psycopg2-binary>=2.9.9,<3" \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/patroni/bin:${PATH}"

COPY patroni.yml /etc/patroni.yml
COPY patroni-entrypoint.sh /usr/local/bin/patroni-entrypoint

RUN chmod +x /usr/local/bin/patroni-entrypoint

ENTRYPOINT ["/usr/local/bin/patroni-entrypoint"]
