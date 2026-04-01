"""
database.py — SQLite 추상화 레이어
나중에 PostgreSQL 등 클라우드 DB로 교체할 때 이 파일만 수정하면 됩니다.
"""
import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_path="assistant.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 결과를 딕셔너리처럼 사용 가능
        return conn

    def _init_db(self):
        """처음 실행 시 테이블을 자동으로 생성합니다."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT    NOT NULL,
                    description TEXT,
                    status      TEXT    DEFAULT 'todo',
                    priority    TEXT    DEFAULT 'medium',
                    due_date    TEXT,
                    due_time    TEXT,
                    category    TEXT,
                    location    TEXT,
                    attendees   TEXT,
                    created_at  TEXT    NOT NULL,
                    updated_at  TEXT    NOT NULL
                )
            """)
            # 기존 DB에 컬럼이 없으면 추가 (앱 업데이트 시 마이그레이션)
            for col in ["location TEXT", "attendees TEXT"]:
                try:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {col}")
                except Exception:
                    pass  # 이미 존재하는 컬럼이면 무시
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # ── 루틴 (Routines) ─────────────────────────────────────────────
            # 이벤트(Tasks)와 독립적으로 반복 체크할 항목을 저장합니다.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routines (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    title         TEXT    NOT NULL,
                    frequency     TEXT    NOT NULL,  -- 'daily' | 'weekly' | 'monthly'
                    days_of_week  TEXT,              -- weekly 전용: JSON 배열 문자열 (예: '[1,3,5]' = 월/수/금)
                    day_of_month  INTEGER,          -- monthly 전용 (예: 1 = 매월 1일)
                    category      TEXT,              -- 선택적 카테고리
                    active        INTEGER DEFAULT 1,-- 1: 활성 / 0: 비활성(삭제)
                    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 루틴 체크 기록: routine_id + checked_date 조합에 대해 완료 여부를 저장합니다.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routine_logs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    routine_id   INTEGER NOT NULL,
                    checked_date DATE    NOT NULL, -- YYYY-MM-DD
                    completed    INTEGER DEFAULT 0,
                    note          TEXT,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (routine_id, checked_date)
                )
            """)
            conn.commit()

    # ── 할 일 (Tasks) ──────────────────────────────────────────────

    def add_task(self, title, description=None, due_date=None,
                 due_time=None, priority="medium", category=None,
                 location=None, attendees=None):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO tasks
                   (title, description, due_date, due_time, priority, category,
                    location, attendees, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'todo', ?, ?)""",
                (title, description, due_date, due_time, priority, category,
                 location, attendees, now, now)
            )
            conn.commit()
            return cursor.lastrowid

    def get_tasks(self, status=None, priority=None, category=None, due_before=None):
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if category:
            query += " AND category = ?"
            params.append(category)
        if due_before:
            query += " AND due_date IS NOT NULL AND due_date <= ?"
            params.append(due_before)
        query += " ORDER BY due_date ASC, priority DESC, created_at ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_task_by_id(self, task_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    def update_task(self, task_id, **kwargs):
        """변경할 필드만 골라서 업데이트합니다."""
        allowed = {"title", "description", "status", "priority",
                   "due_date", "due_time", "category", "location", "attendees"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        fields["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
            conn.commit()
        return True

    def delete_task(self, task_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()

    # ── 대화 기록 (Conversations) ──────────────────────────────────

    def add_message(self, role, content):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, now)
            )
            conn.commit()

    def get_recent_messages(self, limit=20):
        """최근 메시지를 오래된 순서로 반환합니다 (Claude에게 전달용)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [{"role": row["role"], "content": row["content"]}
                    for row in reversed(rows)]

    def clear_conversations(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM conversations")
            conn.commit()
