CREATE TABLE IF NOT EXISTS containment_commands (
    id UUID PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    action JSONB NOT NULL CHECK (jsonb_typeof(action) = 'object'),
    status TEXT NOT NULL DEFAULT 'pending',
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    CONSTRAINT containment_commands_status_check
        CHECK (status IN ('pending', 'claimed', 'completed', 'timed_out'))
);

CREATE INDEX IF NOT EXISTS idx_containment_commands_pending
    ON containment_commands (created_at, id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_containment_commands_expired_lease
    ON containment_commands (lease_expires_at, created_at, id)
    WHERE status = 'claimed';
