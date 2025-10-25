CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS case_events (
  event_id text PRIMARY KEY,
  case_id text NOT NULL,
  source text NOT NULL,
  received_at timestamptz NOT NULL,
  actor_role text,
  actor_name text,
  actor_contact text,
  text text,
  entities jsonb,
  thread_key text,
  emb vector(1536)
);

CREATE TABLE IF NOT EXISTS tasks (
  task_id text PRIMARY KEY,
  case_id text NOT NULL,
  type text NOT NULL,
  status text NOT NULL,
  priority text,
  confidence numeric,
  due_at timestamptz,
  assignee_agent text NOT NULL,
  suggested_action jsonb,
  source_events text[],
  risk_flags text[],
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audits (
  audit_id text PRIMARY KEY,
  ts timestamptz NOT NULL,
  user_email text NOT NULL,
  action text NOT NULL,
  object text NOT NULL,
  why text,
  s3_ref text NOT NULL,
  sha256 text NOT NULL
);
