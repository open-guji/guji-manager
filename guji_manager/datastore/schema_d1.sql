-- 由 d1/gen_schema.py 从线上 Postgres 生成，别手改；改表结构先改生成规则。
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS progress_section (
  "section" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "owner" TEXT,
  "description" TEXT,
  "sort" INTEGER NOT NULL DEFAULT 100,
  PRIMARY KEY ("section"),
  CHECK (length(section) BETWEEN 1 AND 64)
);
CREATE TABLE IF NOT EXISTS imports (
  "import_id" INTEGER PRIMARY KEY,
  "source" TEXT NOT NULL,
  "git_commit" TEXT,
  "actor" TEXT,
  "started_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "finished_at" TEXT,
  "rev_from" INTEGER,
  "rev_to" INTEGER,
  "stats" TEXT
);
CREATE TABLE IF NOT EXISTS workspaces (
  "ws" TEXT NOT NULL,
  "dir" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL DEFAULT 0,
  "raw" TEXT NOT NULL,
  "doc" TEXT,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws")
);
CREATE TABLE IF NOT EXISTS progress_meta (
  "key" TEXT NOT NULL,
  "value" TEXT NOT NULL,
  PRIMARY KEY ("key")
);
CREATE TABLE IF NOT EXISTS progress_metric (
  "book_id" TEXT NOT NULL DEFAULT '',
  "vol" TEXT NOT NULL DEFAULT '',
  "section" TEXT NOT NULL,
  "key" TEXT NOT NULL,
  "label" TEXT NOT NULL,
  "value" REAL,
  "value_text" TEXT,
  "unit" TEXT,
  "detail" TEXT,
  "sort" INTEGER NOT NULL DEFAULT 100,
  "writer" TEXT NOT NULL,
  "at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("book_id", "vol", "section", "key"),
  CHECK (length(key) BETWEEN 1 AND 64),
  FOREIGN KEY (section) REFERENCES progress_section(section)
);
CREATE TABLE IF NOT EXISTS progress_volume (
  "book_id" TEXT NOT NULL,
  "vol" TEXT NOT NULL,
  "book_title" TEXT,
  "vol_title" TEXT,
  "vol_order" INTEGER,
  "ws" TEXT,
  "cv_book" TEXT,
  "stage" TEXT,
  "text_version" TEXT,
  "punct_version" TEXT,
  "entity_version" TEXT,
  "proofing" INTEGER,
  "frozen_version" TEXT,
  "cv_version" TEXT,
  "corpus" TEXT,
  "glyph_pin" TEXT,
  "cells_total" INTEGER,
  "pending_review" INTEGER,
  "human_judged" INTEGER,
  "pending_rev" TEXT,
  "pending_at" TEXT,
  "punct_status" TEXT,
  "note" TEXT,
  "extra" TEXT NOT NULL DEFAULT '{}',
  "field_meta" TEXT NOT NULL DEFAULT '{}',
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("book_id", "vol"),
  CHECK (stage IN ('todo', 'pipeline', 'rough', 'fine', 'released'))
);
CREATE TABLE IF NOT EXISTS anchor_patches_meta (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "sha256" TEXT NOT NULL,
  "bytes" INTEGER NOT NULL,
  "src_line" INTEGER NOT NULL DEFAULT 0,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "src_path"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS anchors (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "event" TEXT NOT NULL,
  "key" TEXT NOT NULL,
  "book" TEXT,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "doc" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "src_path", "event", "key"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS books (
  "ws" TEXT NOT NULL,
  "book" TEXT NOT NULL,
  "title" TEXT,
  "edition" TEXT,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL DEFAULT 0,
  "raw" TEXT NOT NULL,
  "doc" TEXT,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "book"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS changes (
  "rev" INTEGER PRIMARY KEY,
  "import_id" INTEGER,
  "at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tbl" TEXT NOT NULL,
  "op" TEXT NOT NULL,
  "ws" TEXT,
  "pk" TEXT NOT NULL,
  "old_sha" TEXT,
  "new_sha" TEXT,
  FOREIGN KEY (import_id) REFERENCES imports(import_id),
  CHECK (op IN ('insert', 'update', 'delete'))
);
CREATE TABLE IF NOT EXISTS consumed (
  "ws" TEXT NOT NULL,
  "consumer" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "event" TEXT,
  "ts" TEXT,
  "note" TEXT,
  "src_path" TEXT NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "consumer", "src_line"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS corpus_files (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "sha256" TEXT NOT NULL,
  "bytes" INTEGER NOT NULL,
  "src_line" INTEGER NOT NULL DEFAULT 0,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "src_path"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS db_meta (
  "key" TEXT NOT NULL,
  "value" TEXT NOT NULL,
  PRIMARY KEY ("key")
);
CREATE TABLE IF NOT EXISTS events (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "id" TEXT NOT NULL,
  "stream" TEXT NOT NULL,
  "book" TEXT,
  "batch" TEXT,
  "seq" INTEGER,
  "kind" TEXT,
  "actor" TEXT,
  "reviewer" TEXT,
  "ts" TEXT,
  "payload" TEXT,
  "target" TEXT,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "src_path", "id"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS files (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "sha256" TEXT NOT NULL,
  "bytes" INTEGER NOT NULL,
  "src_line" INTEGER NOT NULL DEFAULT 0,
  "raw" TEXT NOT NULL,
  "doc" TEXT,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  "body_r2" INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY ("ws", "src_path"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_admissions (
  "ws" TEXT NOT NULL,
  "instance_id" TEXT NOT NULL,
  "char" TEXT NOT NULL,
  "provenance" TEXT NOT NULL,
  "evidence" TEXT,
  "admitted_at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "instance_id"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_approx_clears (
  "ws" TEXT NOT NULL,
  "instance_id" TEXT NOT NULL,
  "label" TEXT,
  "at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "instance_id", "at"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_approx_labels (
  "ws" TEXT NOT NULL,
  "instance_id" TEXT NOT NULL,
  "label" TEXT NOT NULL,
  "ids" TEXT,
  "note" TEXT,
  "reviewer" TEXT,
  "created_at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "instance_id"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_evictions (
  "ws" TEXT NOT NULL,
  "instance_id" TEXT NOT NULL,
  "char" TEXT,
  "reason" TEXT,
  "at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "instance_id", "at"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_exemplars (
  "ws" TEXT NOT NULL,
  "edition_tag" TEXT NOT NULL,
  "char" TEXT NOT NULL,
  "instance_id" TEXT NOT NULL,
  "role" TEXT NOT NULL,
  "added_at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "edition_tag", "char", "instance_id"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_instances (
  "ws" TEXT NOT NULL,
  "instance_id" TEXT NOT NULL,
  "source_id" TEXT NOT NULL,
  "page" TEXT NOT NULL,
  "col" INTEGER NOT NULL,
  "idx" INTEGER NOT NULL,
  "bbox" TEXT,
  "patch_sha" TEXT,
  "patch_bytes" INTEGER,
  "ink_ratio" REAL,
  "width" REAL,
  "height" REAL,
  "quality_flags" TEXT,
  "label" TEXT,
  "label_status" TEXT,
  "label_confidence" REAL,
  "semantic" TEXT,
  "unicode_cp" INTEGER,
  "ids" TEXT,
  "fidelity" TEXT,
  "fidelity_by" TEXT,
  "updated_at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "instance_id"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_meta (
  "ws" TEXT NOT NULL,
  "key" TEXT NOT NULL,
  "value" TEXT,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "key"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyph_sources (
  "ws" TEXT NOT NULL,
  "source_id" TEXT NOT NULL,
  "collection" TEXT,
  "title" TEXT,
  "volume" TEXT,
  "edition_tag" TEXT NOT NULL,
  "script_style" TEXT,
  "era" TEXT,
  "cols_per_page" INTEGER,
  "chars_per_col" INTEGER,
  "pipeline_version" TEXT,
  "notes" TEXT,
  "kind" TEXT NOT NULL DEFAULT 'woodblock',
  "created_at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "source_id"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS glyphs (
  "ws" TEXT NOT NULL,
  "edition_tag" TEXT NOT NULL,
  "char" TEXT NOT NULL,
  "semantic" TEXT,
  "unicode_cp" INTEGER,
  "ids" TEXT,
  "status" TEXT NOT NULL DEFAULT 'sparse',
  "n_confirmed" INTEGER NOT NULL DEFAULT 0,
  "updated_at" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "edition_tag", "char"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS source_files (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "tbl" TEXT NOT NULL,
  "sha256" TEXT NOT NULL,
  "bytes" INTEGER NOT NULL,
  "n_lines" INTEGER NOT NULL,
  "final_newline" INTEGER NOT NULL,
  "src_line" INTEGER NOT NULL DEFAULT 0,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "src_path")
);
CREATE TABLE IF NOT EXISTS pending_items (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "item_id" TEXT,
  "ver" INTEGER,
  "book" TEXT NOT NULL,
  "vol" TEXT NOT NULL,
  "cell" TEXT,
  "state" TEXT,
  "op" TEXT,
  "src" TEXT,
  "actor" TEXT,
  "at" TEXT,
  "why" TEXT,
  "recheck" INTEGER NOT NULL DEFAULT 0,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  -- 待审条目（feedback/lists/pending/<书>/<章>.items.jsonl）一行一个版本，GM4 11-26 从 files 拆出；u 由 raw 现算
  "u" INTEGER GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.u') = 'integer' THEN json_extract(raw, '$.u') END) VIRTUAL,
  PRIMARY KEY ("ws", "src_path", "src_line"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS list_rows (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "dataset" TEXT NOT NULL,
  "book" TEXT,
  "name" TEXT NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  -- feedback/lists 下的 jsonl 清单一行一条（web／opinions／freeze／ledger／u_void），GM4 11-26；id、u 由 raw 现算
  "id" TEXT GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.id') = 'text' THEN json_extract(raw, '$.id') END) VIRTUAL,
  "u" INTEGER GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.u') = 'integer' THEN json_extract(raw, '$.u') END) VIRTUAL,
  PRIMARY KEY ("ws", "src_path", "src_line"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS ai_notes (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "vol" TEXT NOT NULL,
  "cell" TEXT,
  "batch" TEXT,
  "level" TEXT,
  "model" TEXT,
  "char" TEXT,
  "conf" TEXT,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  -- AI 分析摘要（feedback/notes/<册>.jsonl 一行一条，浅层、深搜、放行与不确定都写；GM3 11-27）；book、u、状态由 raw 现算
  "book" TEXT GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.book') = 'text' THEN json_extract(raw, '$.book') END) VIRTUAL,
  "u" INTEGER GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.u') = 'integer' THEN json_extract(raw, '$.u') END) VIRTUAL,
  "st" TEXT GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.st') = 'text' THEN json_extract(raw, '$.st') END) VIRTUAL,
  PRIMARY KEY ("ws", "src_path", "src_line"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS verdicts (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "id" TEXT NOT NULL,
  "task" TEXT NOT NULL,
  "status" TEXT,
  "label_origin" TEXT,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "doc" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  PRIMARY KEY ("ws", "src_path", "id"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE INDEX IF NOT EXISTS changes_tbl_ws ON changes (tbl, ws, rev);
CREATE INDEX IF NOT EXISTS consumed_event ON consumed (ws, consumer, event);
CREATE INDEX IF NOT EXISTS events_ws_batch ON events (ws, batch);
CREATE INDEX IF NOT EXISTS events_ws_book ON events (ws, book);
CREATE INDEX IF NOT EXISTS events_ws_id ON events (ws, id);
CREATE INDEX IF NOT EXISTS list_rows_ds ON list_rows (ws, dataset, book, name, src_line);
CREATE INDEX IF NOT EXISTS ai_notes_u ON ai_notes (ws, book, u) WHERE u IS NOT NULL;
CREATE INDEX IF NOT EXISTS pending_items_item ON pending_items (ws, src_path, item_id, src_line);
CREATE INDEX IF NOT EXISTS pending_items_u ON pending_items (ws, book, u) WHERE u IS NOT NULL;
CREATE INDEX IF NOT EXISTS glyph_instances_label ON glyph_instances (ws, label) WHERE (label IS NOT NULL);
CREATE INDEX IF NOT EXISTS glyph_instances_sha ON glyph_instances (patch_sha);

-- 每个待审条目的当前版本＝该条目在文件里的最后一行（两边各自追加的版本都留，GM4 11-26）
CREATE VIEW IF NOT EXISTS pending_current AS SELECT p.* FROM pending_items p
  WHERE p.src_line = (SELECT max(q.src_line) FROM pending_items q
                      WHERE q.ws = p.ws AND q.src_path = p.src_path AND q.item_id = p.item_id);
CREATE VIEW IF NOT EXISTS lists AS SELECT * FROM files WHERE kind = 'list';
CREATE VIEW IF NOT EXISTS batches AS SELECT * FROM files WHERE kind = 'batch';

-- 提交守卫（见 worker/src/db.ts guardStmt）：批里写 0 就 CHECK 失败、整批回滚
CREATE TABLE IF NOT EXISTS _guard (ok INTEGER NOT NULL CHECK (ok = 1));
