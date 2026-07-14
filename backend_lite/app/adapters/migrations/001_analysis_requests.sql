CREATE TABLE IF NOT EXISTS analysis_requests (
    analysis_request_pk INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    idempotency_key_version TEXT NULL,
    idempotency_key_digest TEXT NULL CHECK (
        idempotency_key_digest IS NULL OR (
            length(idempotency_key_digest) = 64
            AND idempotency_key_digest NOT GLOB '*[^0-9a-f]*'
        )
    ),
    fingerprint_version TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL CHECK (
        length(request_fingerprint) = 64
        AND request_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (status IN (
        'RECEIVED', 'PROCESSING', 'COMPLETE',
        'FAILED_RETRYABLE', 'FAILED_FINAL'
    )),
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
    requested_chat_id TEXT NULL,
    chat_id TEXT NOT NULL,
    user_type TEXT NOT NULL,
    language TEXT NOT NULL,
    user_message_id TEXT NOT NULL,
    assistant_message_id TEXT NULL,
    response_payload TEXT NULL,
    error_class TEXT NULL CHECK (
        error_class IS NULL OR error_class IN (
            'client', 'retryable_dependency', 'final_deterministic', 'internal'
        )
    ),
    last_error_code TEXT NULL,
    error_details_json TEXT NULL,
    contract_version TEXT NOT NULL,
    corpus_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    retriever_version TEXT NOT NULL,
    generator_mode TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processing_started_at TEXT NOT NULL,
    processing_deadline_at TEXT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT NULL,
    failed_at TEXT NULL,
    UNIQUE (session_id, request_id),
    UNIQUE (user_message_id),
    CHECK ((idempotency_key_version IS NULL) = (idempotency_key_digest IS NULL)),
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id),
    FOREIGN KEY (user_message_id) REFERENCES messages(message_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (assistant_message_id) REFERENCES messages(message_id)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK ((status = 'COMPLETE') = (assistant_message_id IS NOT NULL)),
    CHECK ((status IN ('COMPLETE', 'FAILED_FINAL')) = (response_payload IS NOT NULL)),
    CHECK ((status = 'COMPLETE') = (completed_at IS NOT NULL)),
    CHECK ((status IN ('FAILED_RETRYABLE', 'FAILED_FINAL')) = (failed_at IS NOT NULL)),
    CHECK ((status IN ('FAILED_RETRYABLE', 'FAILED_FINAL')) = (error_class IS NOT NULL)),
    CHECK ((status IN ('FAILED_RETRYABLE', 'FAILED_FINAL')) = (last_error_code IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_analysis_requests_assistant_message
    ON analysis_requests(assistant_message_id)
    WHERE assistant_message_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_analysis_requests_session_idempotency
    ON analysis_requests(session_id, idempotency_key_digest)
    WHERE idempotency_key_digest IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_analysis_requests_status_updated
    ON analysis_requests(status, updated_at);
CREATE INDEX IF NOT EXISTS ix_analysis_requests_chat_created
    ON analysis_requests(chat_id, created_at, analysis_request_pk);
