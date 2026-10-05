CREATE SEQUENCE IF NOT EXISTS token_revision_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE token_credentials (
    user_account VARCHAR(128) PRIMARY KEY,
    encrypted_password TEXT,
    encrypted_token TEXT NOT NULL,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    real_name VARCHAR(200) NOT NULL DEFAULT '',
    department VARCHAR(300) NOT NULL DEFAULT '',
    auth_method VARCHAR(32) NOT NULL,
    revision BIGINT NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_token_credentials_revision ON token_credentials (revision);
CREATE INDEX idx_token_credentials_updated_at ON token_credentials (updated_at DESC);

CREATE TABLE service_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
