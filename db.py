# -*- coding: utf-8 -*-
"""SQLite 访问层：建表、查询、JSON 辅助。

本地用 SQLite；云上把 config.DB_PATH 换成 MySQL 时，
只需替换 connect()/占位符，业务 SQL 保持标准写法。
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta

from config import DB_PATH, DATA_DIR

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'student',
  college TEXT DEFAULT '',
  avatar TEXT DEFAULT '',
  cover TEXT DEFAULT '',
  signature TEXT DEFAULT '',
  interests TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS floors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  building TEXT NOT NULL,
  floor_no INTEGER NOT NULL,
  plan_w INTEGER DEFAULT 960,
  plan_h INTEGER DEFAULT 620,
  plan_path TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS buildings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  code TEXT DEFAULT '',
  lat REAL NOT NULL,
  lng REAL NOT NULL,
  address TEXT DEFAULT '',
  description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS seats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  floor_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  zone TEXT NOT NULL,
  x REAL NOT NULL, y REAL NOT NULL, w REAL DEFAULT 28, h REAL DEFAULT 22,
  seat_type TEXT DEFAULT 'normal',
  features TEXT DEFAULT '',
  status TEXT DEFAULT 'free'
);
CREATE TABLE IF NOT EXISTS nav_nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  floor_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  x REAL NOT NULL, y REAL NOT NULL,
  kind TEXT DEFAULT 'corridor'
);
CREATE TABLE IF NOT EXISTS nav_edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  floor_id INTEGER NOT NULL,
  from_node TEXT NOT NULL,
  to_node TEXT NOT NULL,
  distance REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  seat_id INTEGER NOT NULL,
  subject TEXT DEFAULT '',
  goal TEXT DEFAULT '',
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  checkin_at TEXT,
  checkout_at TEXT,
  status TEXT NOT NULL DEFAULT 'booked',
  source TEXT DEFAULT 'web',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reservation_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  seat_id INTEGER NOT NULL,
  subject TEXT DEFAULT '',
  started_at TEXT NOT NULL,
  ended_at TEXT,
  duration_min INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',
  stuck_points TEXT DEFAULT '',
  relay_content_id INTEGER,
  pushed_at TEXT,
  feedback TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER,
  title TEXT NOT NULL,
  subject TEXT DEFAULT '',
  knowledge_point TEXT DEFAULT '',
  description TEXT DEFAULT '',
  source_type TEXT DEFAULT 'student',
  file_path TEXT DEFAULT '',
  cover_path TEXT DEFAULT '',
  duration_sec REAL DEFAULT 0,
  status TEXT DEFAULT 'processing',
  ai_summary TEXT DEFAULT '',
  ai_risk REAL DEFAULT 0,
  review_note TEXT DEFAULT '',
  reviewer_id INTEGER,
  reviewed_at TEXT,
  published_at TEXT,
  views INTEGER DEFAULT 0,
  helpful INTEGER DEFAULT 0,
  unhelpful INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS content_frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER NOT NULL,
  idx INTEGER NOT NULL,
  ts_sec REAL DEFAULT 0,
  path TEXT NOT NULL,
  risk REAL DEFAULT 0,
  labels TEXT DEFAULT '',
  reasons TEXT DEFAULT '',
  status TEXT DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id INTEGER NOT NULL,
  reviewer_id INTEGER NOT NULL,
  decision TEXT NOT NULL,
  note TEXT DEFAULT '',
  checklist TEXT DEFAULT '',
  frames_reviewed INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  kind TEXT DEFAULT 'system',
  title TEXT NOT NULL,
  body TEXT DEFAULT '',
  payload TEXT DEFAULT '',
  read INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relay_pushes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  content_id INTEGER NOT NULL,
  reason TEXT DEFAULT '',
  score_json TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  opened_at TEXT,
  feedback TEXT
);
CREATE TABLE IF NOT EXISTS workflow_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  flow_key TEXT NOT NULL,
  title TEXT DEFAULT '',
  trigger TEXT DEFAULT '',
  status TEXT DEFAULT 'running',
  context TEXT DEFAULT '',
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS workflow_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  node_id TEXT NOT NULL,
  node_name TEXT NOT NULL,
  status TEXT DEFAULT 'running',
  detail TEXT DEFAULT '',
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  session_id INTEGER,
  intent TEXT DEFAULT '',
  input TEXT DEFAULT '',
  output TEXT DEFAULT '',
  tool_calls TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT DEFAULT ''
);
'''


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    # 轻量迁移：已有库补楼层底图字段
    cols = {row[1] for row in conn.execute('PRAGMA table_info(floors)').fetchall()}
    if 'plan_path' not in cols:
        conn.execute("ALTER TABLE floors ADD COLUMN plan_path TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def query(sql, args=()):
    conn = connect()
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def one(sql, args=()):
    conn = connect()
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def execute(sql, args=()):
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def executemany(sql, seq):
    conn = connect()
    try:
        conn.executemany(sql, seq)
        conn.commit()
    finally:
        conn.close()


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def parse(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')


def minutes_between(a, b):
    return max(0, int((parse(b) - parse(a)).total_seconds() // 60))


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def loads(s, default=None):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def get_setting(key, default=''):
    r = one('SELECT value FROM settings WHERE key=?', (key,))
    return r['value'] if r else default


def set_setting(key, value):
    execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (key, str(value)))


if __name__ == '__main__':
    init_db()
    print('DB ready:', DB_PATH)
