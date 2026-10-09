CREATE TABLE generation_creation_requests (
    request_id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    result_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
