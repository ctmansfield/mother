-- 0002_behavior_events.sql
CREATE TABLE IF NOT EXISTS behavior_events (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  action_id UUID,
  event TEXT NOT NULL,               -- completed|snoozed|skipped
  latency_s INT,
  context JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
