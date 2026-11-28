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
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  -- 与线上一致（11-24 起 payload／target、11-26 起 u／level 由 raw 现算，虚拟列，不能 INSERT；线上另有改名留下的 payload_old／target_old，全 NULL，不建）
  payload TEXT GENERATED ALWAYS AS (raw -> '$.payload') VIRTUAL,
  target TEXT GENERATED ALWAYS AS (raw -> '$.target') VIRTUAL,
  u INTEGER GENERATED ALWAYS AS (COALESCE(
       CASE WHEN json_type(raw, '$.target.anchor.u') = 'integer' THEN json_extract(raw, '$.target.anchor.u') END,
       CASE WHEN json_type(raw, '$.payload.u') = 'integer' THEN json_extract(raw, '$.payload.u') END)) VIRTUAL,
  level TEXT GENERATED ALWAYS AS (CASE
       WHEN stream = 'uid' THEN 'ledger'
       WHEN stream IN ('rulings', 'vision', 'vis_glyph') THEN 'ai'      -- vis_glyph：cv 第三步看图缓存，不论 actor/source 一律 ai（CV3 11-28）
       WHEN json_extract(raw, '$.payload.source') IN ('auto', 'knn_infer') THEN 'machine'
       WHEN json_extract(raw, '$.payload.source') IN ('llm', 'vision') THEN 'model'
       WHEN json_extract(raw, '$.payload.level') IN ('human', 'ai', 'machine') THEN json_extract(raw, '$.payload.level')
       WHEN kind IN ('needs_review', 'cell_review', 'admit_candidate') THEN 'note'
       WHEN COALESCE(actor, 'user') <> 'model' THEN 'human'
       WHEN (CASE WHEN instr(batch, '~') > 0 THEN substr(batch, 1, instr(batch, '~') - 1) ELSE batch END) IN (
            'H-mojibake-fix-20260927', 'r74-v01', 'r77-重绑', 'r79-v01', 'SJ-ry-rebind-1120', 'SJ-sheldon-1123',
            'SJ-L1取消归一-human24', 'SJ-v02-rebind-1124', 'SJ-歲暫歸一-1125') THEN 'human'
       ELSE 'ai' END) VIRTUAL,
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
  "reason" TEXT GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.doc.pending_reason') = 'text' THEN json_extract(raw, '$.doc.pending_reason') END) VIRTUAL,
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
  "book" TEXT,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  -- 第三步 AI 分析摘要（feedback/notes/<册>.jsonl）一格一轮一行，GM3 请、CV0 11-27 建；以下由 raw 现算（取 trace 最后一轮），manager 别写这几列
  "u" INTEGER GENERATED ALWAYS AS (CASE WHEN json_type(raw, '$.u') = 'integer' THEN json_extract(raw, '$.u') END) VIRTUAL,
  "batch" TEXT GENERATED ALWAYS AS (json_extract(raw, '$.batch')) VIRTUAL,
  "char" TEXT GENERATED ALWAYS AS (json_extract(raw, '$.trace[#-1].char')) VIRTUAL,
  "conf" TEXT GENERATED ALWAYS AS (json_extract(raw, '$.trace[#-1].conf')) VIRTUAL,
  "st" TEXT GENERATED ALWAYS AS (json_extract(raw, '$.trace[#-1].status')) VIRTUAL,
  "lv" TEXT GENERATED ALWAYS AS (json_extract(raw, '$.trace[#-1].level')) VIRTUAL,
  "model" TEXT GENERATED ALWAYS AS (json_extract(raw, '$.trace[#-1].model')) VIRTUAL,
  PRIMARY KEY ("ws", "src_path", "src_line"),
  FOREIGN KEY (ws) REFERENCES workspaces(ws)
);
CREATE TABLE IF NOT EXISTS file_chunks (
  "ws" TEXT NOT NULL,
  "src_path" TEXT NOT NULL,
  "src_line" INTEGER NOT NULL,
  "raw" TEXT NOT NULL,
  "rev" INTEGER NOT NULL,
  "ingested_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "row_sha" TEXT,
  -- 超过 D1 单行上限、又不是逐行 json 的整文件（两张超大整张待审单）按 30 万字符切块，src_line＝块号；拼回不加换行，GM4 11-27
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

-- 11-28 CV0 对齐线上 guji-data-main（这些索引、视图线上早已手加）
CREATE INDEX IF NOT EXISTS events_ws_book_u ON events (ws, book, u) WHERE u IS NOT NULL;
CREATE INDEX IF NOT EXISTS events_ws_u ON events (ws, u) WHERE u IS NOT NULL;
CREATE INDEX IF NOT EXISTS changes_ws_rev ON changes (ws, rev);
CREATE INDEX IF NOT EXISTS consumed_src ON consumed (ws, src_path, consumer, src_line);
CREATE INDEX IF NOT EXISTS glyph_admissions_src ON glyph_admissions (ws, src_path, instance_id);
CREATE INDEX IF NOT EXISTS glyph_exemplars_src ON glyph_exemplars (ws, src_path, edition_tag, char, instance_id);
CREATE INDEX IF NOT EXISTS glyph_instances_src ON glyph_instances (ws, src_path, instance_id);
CREATE VIEW IF NOT EXISTS voids AS
WITH ul AS (
  SELECT ws, src_path, src_line, COALESCE(book, json_extract(raw, '$.book')) AS book,
         json_extract(raw, '$.kind') AS kind, json_extract(raw, '$.id') AS ref,
         json_extract(raw, '$.stream') AS stream, json_extract(raw, '$.key') AS cell,
         json_extract(raw, '$.reason') AS reason, json_extract(raw, '$.by') AS by, json_extract(raw, '$.at') AS at
  FROM list_rows WHERE dataset = 'u_void'
), ulr AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY ws, src_path, COALESCE(ref, stream || '/' || cell) ORDER BY src_line DESC) AS rn
  FROM ul
), ps AS (
  SELECT ws, src_path, src_line, book, id AS event_id,
         json_extract(raw, '$.payload.pin_id') AS pin_id, json_extract(raw, '$.payload.v') AS v,
         json_extract(raw, '$.payload.reason') AS reason, json_extract(raw, '$.payload.by') AS by, ts,
         ROW_NUMBER() OVER (PARTITION BY ws, json_extract(raw, '$.payload.pin_id') ORDER BY ts DESC, src_line DESC) AS rn
  FROM events WHERE stream = 'pin_state'
)
SELECT ws, book, 'u_void' AS src, COALESCE(ref, stream || '/' || cell) AS ref, cell, reason, by, at, src_path, src_line
FROM ulr WHERE rn = 1 AND kind = 'u_void'
UNION ALL
SELECT ws, book, 'pin_state' AS src, pin_id AS ref, NULL AS cell, reason, by, ts AS at, src_path, src_line
FROM ps WHERE rn = 1 AND v = 'removed';
