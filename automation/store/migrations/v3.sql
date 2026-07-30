-- Schema v3: user automation settings + scan schedule

CREATE TABLE IF NOT EXISTS user_settings (
    tenant_id TEXT NOT NULL DEFAULT 'default',
    key TEXT NOT NULL,
    value_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tenant_id, key)
);

CREATE INDEX IF NOT EXISTS idx_user_settings_tenant ON user_settings(tenant_id);
