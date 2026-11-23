-- 任务库 D1 版（2026-11-22 用户定从美国机 Postgres 搬到 Cloudflare D1 独立库 guji-jobs）。
-- 同 schema.sql 的表与列，按 SQLite 改写：时间是 ISO 文本（UTC，毫秒），jsonb/数组是 JSON 文本，布尔是 0/1。
-- 多一列 mark：D1 没有交互式事务，一批语句里「刚改的那几行」靠本次随机标记找（见 store_d1.py）。
-- 幂等，可反复执行。经 Cloudflare D1 REST 或 wrangler 执行（Worker 的 /v1/sql 不收 DDL）。

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  kind             TEXT NOT NULL,
  book             TEXT,
  book_id          TEXT,
  spec             TEXT NOT NULL,                 -- JSON，提交后不改
  spec_hash        TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'blocked', 'cancelled', 'duplicate')),
  priority         INTEGER NOT NULL DEFAULT 100,
  depends_on       TEXT NOT NULL DEFAULT '[]',    -- JSON 数组（任务号）
  duplicate_of     INTEGER REFERENCES job (id),
  submitted_by     TEXT NOT NULL,
  why              TEXT,
  stage            TEXT,
  progress         TEXT,
  attempts         INTEGER NOT NULL DEFAULT 0,
  max_attempts     INTEGER NOT NULL DEFAULT 3,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  error            TEXT,
  run_after        TEXT,
  notified_at      TEXT,
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  started_at       TEXT,
  finished_at      TEXT,
  updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  mark             TEXT
);
CREATE INDEX IF NOT EXISTS job_queued ON job (priority, created_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS job_hash ON job (spec_hash);
CREATE INDEX IF NOT EXISTS job_book ON job (book, created_at);
CREATE INDEX IF NOT EXISTS job_book_id ON job (book_id, book, created_at);
CREATE INDEX IF NOT EXISTS job_mark ON job (mark) WHERE mark IS NOT NULL;
CREATE INDEX IF NOT EXISTS job_active_by ON job (submitted_by) WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS job_unnotified ON job (submitted_by)
  WHERE notified_at IS NULL AND status IN ('succeeded', 'failed', 'blocked', 'cancelled');
CREATE INDEX IF NOT EXISTS job_waiting_deps ON job (id) WHERE status = 'queued' AND depends_on <> '[]';
-- 同一册同时只跑一条（锁的是（书 ID，册号））
CREATE UNIQUE INDEX IF NOT EXISTS job_one_running_per_book ON job (coalesce(book_id, ''), book)
  WHERE status = 'running' AND book IS NOT NULL;

CREATE TABLE IF NOT EXISTS attempt (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id       INTEGER NOT NULL REFERENCES job (id) ON DELETE CASCADE,
  n            INTEGER NOT NULL,
  worker       TEXT NOT NULL,
  session      TEXT,
  host         TEXT,
  cv_commit    TEXT,
  started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  heartbeat_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  lease_until  TEXT NOT NULL,
  finished_at  TEXT,
  outcome      TEXT CHECK (outcome IN ('succeeded', 'failed', 'blocked', 'cancelled', 'lost')),
  exit_code    INTEGER,
  log_tail     TEXT,
  mark         TEXT,
  UNIQUE (job_id, n)
);
CREATE INDEX IF NOT EXISTS attempt_live ON attempt (lease_until) WHERE finished_at IS NULL;
CREATE INDEX IF NOT EXISTS attempt_mark ON attempt (mark) WHERE mark IS NOT NULL;

CREATE TABLE IF NOT EXISTS event (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id     INTEGER NOT NULL REFERENCES job (id) ON DELETE CASCADE,
  attempt_id INTEGER REFERENCES attempt (id) ON DELETE CASCADE,
  at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  stage      TEXT,
  level      TEXT NOT NULL DEFAULT 'info' CHECK (level IN ('info', 'warn', 'error')),
  msg        TEXT NOT NULL,
  secs       REAL,
  data       TEXT
);
CREATE INDEX IF NOT EXISTS event_job ON event (job_id, id);

CREATE TABLE IF NOT EXISTS result (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id     INTEGER NOT NULL REFERENCES job (id) ON DELETE CASCADE,
  attempt_id INTEGER REFERENCES attempt (id) ON DELETE SET NULL,
  kind       TEXT NOT NULL CHECK (kind IN ('pack', 'diff', 'check', 'output', 'file')),
  name       TEXT NOT NULL,
  location   TEXT,
  data       TEXT,
  at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS result_job ON result (job_id);

CREATE TABLE IF NOT EXISTS worker (
  name       TEXT PRIMARY KEY,
  session    TEXT,
  host       TEXT,
  runner     TEXT,
  state      TEXT NOT NULL DEFAULT 'idle' CHECK (state IN ('idle', 'busy', 'stopped')),
  job_id     INTEGER REFERENCES job (id) ON DELETE SET NULL,
  done       INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  note       TEXT
);

CREATE TABLE IF NOT EXISTS perf_run (
  run_id      TEXT PRIMARY KEY,
  grp         TEXT,
  book        TEXT NOT NULL,
  book_id     TEXT,
  pipeline    TEXT,
  steps       TEXT,           -- JSON 数组
  n_pages     INTEGER,
  jobs        INTEGER,
  force       INTEGER,
  job_id      INTEGER,
  cv_version  TEXT,
  cv_commit   TEXT,
  host        TEXT,
  machine     TEXT,
  argv        TEXT,
  started_at  TEXT,
  finished_at TEXT,
  wall_s      REAL,
  stopped     INTEGER,
  pushed_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS perf_run_started ON perf_run (started_at);
CREATE INDEX IF NOT EXISTS perf_run_book ON perf_run (book, started_at);
CREATE INDEX IF NOT EXISTS perf_run_job ON perf_run (job_id) WHERE job_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS perf_step (
  run_id       TEXT NOT NULL,
  step         TEXT NOT NULL,
  pages        INTEGER,
  ok           INTEGER,
  skipped      INTEGER,
  failed       INTEGER,
  jobs         INTEGER,
  wall_s       REAL,
  compute_s    REAL,
  p50_s        REAL,
  p90_s        REAL,
  max_s        REAL,
  parallel_eff REAL,
  cpu_s        REAL,
  child_cpu_s  REAL,
  peak_rss_mb  INTEGER,
  overhead     TEXT,
  spans        TEXT,
  counts       TEXT,
  slowest      TEXT,
  PRIMARY KEY (run_id, step)
);
CREATE INDEX IF NOT EXISTS perf_step_step ON perf_step (step);

INSERT INTO meta (key, value) VALUES ('schema_version', 'd1-1')
  ON CONFLICT (key) DO UPDATE SET value = excluded.value;
