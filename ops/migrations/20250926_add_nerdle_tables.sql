BEGIN;

-- If you ever want uuid generation; harmless if unused.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Core game table
CREATE TABLE IF NOT EXISTS nerdle_game (
  id            text PRIMARY KEY,               -- your app can supply uuid/hex; kept as text for flexibility
  user_id       text        NOT NULL,
  difficulty    text        NOT NULL DEFAULT 'normal',  -- e.g. easy|normal|hard
  target_expr   text        NOT NULL,           -- the secret equation, e.g. "12+3*4=24"
  target_value  numeric,                        -- optional cache of result
  length        smallint    NOT NULL,           -- length of the puzzle string
  max_guesses   smallint    NOT NULL DEFAULT 6,
  guess_count   smallint    NOT NULL DEFAULT 0,
  status        text        NOT NULL DEFAULT 'active',  -- active|won|lost
  started_at    timestamptz NOT NULL DEFAULT now(),
  completed_at  timestamptz,
  CHECK (status IN ('active','won','lost'))
);

CREATE INDEX IF NOT EXISTS idx_nerdle_game_user_started
  ON nerdle_game(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_nerdle_game_status
  ON nerdle_game(status);

-- Per-guess table
CREATE TABLE IF NOT EXISTS nerdle_guess (
  id         bigserial PRIMARY KEY,
  game_id    text        NOT NULL REFERENCES nerdle_game(id) ON DELETE CASCADE,
  user_id    text        NOT NULL,
  guess      text        NOT NULL,              -- raw guess string, e.g. "12+3*4=24"
  feedback   jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- per-char feedback if you store it
  is_valid   boolean     NOT NULL DEFAULT true,          -- equation validity/parse check
  error      text,                                          -- reason if invalid
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nerdle_guess_game
  ON nerdle_guess(game_id, created_at);
CREATE INDEX IF NOT EXISTS idx_nerdle_guess_user
  ON nerdle_guess(user_id, created_at);

-- Compatibility: pluralized names that some codebases use
CREATE OR REPLACE VIEW nerdle_games   AS SELECT * FROM nerdle_game;
CREATE OR REPLACE VIEW nerdle_guesses AS SELECT * FROM nerdle_guess;

-- Allow INSERTs through the plural views (INSTEAD OF triggers)
CREATE OR REPLACE FUNCTION _nerdle_games_ins() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO nerdle_game(
    id,user_id,difficulty,target_expr,target_value,length,
    max_guesses,guess_count,status,started_at,completed_at
  )
  VALUES (
    COALESCE(NEW.id, encode(gen_random_bytes(16),'hex')),
    NEW.user_id, COALESCE(NEW.difficulty,'normal'),
    NEW.target_expr, NEW.target_value, NEW.length,
    COALESCE(NEW.max_guesses,6), COALESCE(NEW.guess_count,0),
    COALESCE(NEW.status,'active'), COALESCE(NEW.started_at, now()), NEW.completed_at
  );
  RETURN NEW;
END$$;
DROP TRIGGER IF EXISTS _ins ON nerdle_games;
CREATE TRIGGER _ins
  INSTEAD OF INSERT ON nerdle_games
  FOR EACH ROW EXECUTE FUNCTION _nerdle_games_ins();

CREATE OR REPLACE FUNCTION _nerdle_guesses_ins() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO nerdle_guess(
    game_id,user_id,guess,feedback,is_valid,error,created_at
  )
  VALUES (
    NEW.game_id, NEW.user_id, NEW.guess,
    COALESCE(NEW.feedback,'{}'::jsonb),
    COALESCE(NEW.is_valid,true), NEW.error, COALESCE(NEW.created_at, now())
  );
  RETURN NEW;
END$$;
DROP TRIGGER IF EXISTS _ins ON nerdle_guesses;
CREATE TRIGGER _ins
  INSTEAD OF INSERT ON nerdle_guesses
  FOR EACH ROW EXECUTE FUNCTION _nerdle_guesses_ins();

COMMIT;
