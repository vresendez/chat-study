CREATE TABLE IF NOT EXISTS participants (
  id TEXT PRIMARY KEY,          -- lowercased code or email, imported from the survey
  created_at DOUBLE PRECISION,
  consented_at DOUBLE PRECISION,
  last_login DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY,
  participant TEXT NOT NULL REFERENCES participants(id),
  conversation_id TEXT NOT NULL,
  model TEXT NOT NULL,
  role TEXT NOT NULL,           -- 'user' or 'assistant'
  content TEXT NOT NULL,
  ts DOUBLE PRECISION NOT NULL, -- unix seconds
  latency_ms INTEGER            -- assistant rows only: time to full reply
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(participant, conversation_id, id);

CREATE TABLE IF NOT EXISTS hidden_conversations (
  participant TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  ts DOUBLE PRECISION,          -- when the participant deleted it (data is kept for research)
  PRIMARY KEY (participant, conversation_id)
);

CREATE TABLE IF NOT EXISTS events (
  id BIGSERIAL PRIMARY KEY,
  participant TEXT,
  type TEXT NOT NULL,           -- login, logout, new_chat, open_chat, delete_chat, download_chat, model_change, page_view
  conversation_id TEXT,
  detail TEXT,
  ts DOUBLE PRECISION NOT NULL
);
