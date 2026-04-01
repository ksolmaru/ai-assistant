"""
database.py — SQLite 추상화 레이어
나중에 PostgreSQL 등 클라우드 DB로 교체할 때 이 파일만 수정하면 됩니다.
"""
import sqlite3
import json
from datetime import datetime, date, timedelta


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

    # ── 루틴 (Routines) ──────────────────────────────────────────────────

    def add_routine(self, title, frequency, days_of_week=None, day_of_month=None, category=None, active=1):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO routines
                    (title, frequency, days_of_week, day_of_month, category, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, frequency, days_of_week, day_of_month, category, active, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_routines(self, active_only=True):
        query = "SELECT * FROM routines"
        params: list = []
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY id DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def update_routine(self, routine_id, **kwargs):
        allowed = {"title", "frequency", "days_of_week", "day_of_month", "category", "active"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [routine_id]

        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE routines SET {set_clause} WHERE id = ?",
                values,
            )
            conn.commit()
            return cur.rowcount > 0

    def deactivate_routine(self, routine_id):
        # 기획서에서는 “삭제(비활성화)”로 되어 있으므로 active=0 처리합니다.
        with self._connect() as conn:
            cur = conn.execute("UPDATE routines SET active = 0 WHERE id = ?", (routine_id,))
            conn.commit()
            return cur.rowcount > 0

    def set_routine_check(self, routine_id, checked_date: str, completed: int, note=None):
        # UNIQUE (routine_id, checked_date) 때문에 “업데이트 후 없으면 인서트” 패턴을 사용합니다.
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE routine_logs
                SET completed = ?, note = ?
                WHERE routine_id = ? AND checked_date = ?
                """,
                (int(completed), note, routine_id, checked_date),
            ).rowcount

            if updated == 0:
                conn.execute(
                    """
                    INSERT INTO routine_logs (routine_id, checked_date, completed, note)
                    VALUES (?, ?, ?, ?)
                    """,
                    (routine_id, checked_date, int(completed), note),
                )
            conn.commit()
            return True

    def _parse_days_of_week(self, days_of_week):
        if not days_of_week:
            return []
        try:
            v = json.loads(days_of_week) if isinstance(days_of_week, str) else days_of_week
            if isinstance(v, list):
                return [int(x) for x in v]
        except Exception:
            pass
        return []

    def _day_num_monday_1(self, d: date) -> int:
        # datetime.date.weekday(): Mon=0..Sun=6  ->  Mon=1..Sun=7 로 변환
        return int(d.weekday()) + 1

    def _routine_applies_on_date(self, routine: dict, d: date) -> bool:
        freq = (routine.get("frequency") or "").lower().strip()
        if freq == "daily":
            return True
        if freq == "weekly":
            allowed = self._parse_days_of_week(routine.get("days_of_week"))
            return self._day_num_monday_1(d) in allowed
        if freq == "monthly":
            dom = routine.get("day_of_month")
            if dom is None:
                return False
            return int(dom) == int(d.day)
        return False

    def get_routines_for_date(self, checked_date: str):
        d = datetime.strptime(checked_date, "%Y-%m-%d").date()
        routines = self.get_routines(active_only=True)
        applicable = [r for r in routines if self._routine_applies_on_date(r, d)]
        routine_ids = [r["id"] for r in applicable]
        logs_map = {}
        if routine_ids:
            placeholders = ", ".join("?" for _ in routine_ids)
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT routine_id, completed
                    FROM routine_logs
                    WHERE checked_date = ? AND routine_id IN ({placeholders})
                    """,
                    [checked_date] + routine_ids,
                ).fetchall()
                logs_map = {(row["routine_id"], checked_date): int(row["completed"]) for row in rows}

        result = []
        for r in applicable:
            completed = logs_map.get((r["id"], checked_date), 0)
            result.append({
                "id": r["id"],
                "title": r["title"],
                "frequency": r["frequency"],
                "days_of_week": r.get("days_of_week"),
                "day_of_month": r.get("day_of_month"),
                "category": r.get("category"),
                "completed": completed,
            })
        return result

    def get_routines_weekly_matrix(self, week_start: str):
        # week_start: YYYY-MM-DD (월요일로 가정)
        ws = datetime.strptime(week_start, "%Y-%m-%d").date()
        week_days = [ws + timedelta(days=i) for i in range(7)]
        week_day_strs = [d.strftime("%Y-%m-%d") for d in week_days]

        routines = self.get_routines(active_only=True)
        routine_ids = [r["id"] for r in routines]

        # 해당 주 전체 범위에 대한 로그를 미리 가져옵니다.
        logs_map: dict[tuple[int, str], int] = {}
        if routine_ids:
            placeholders = ", ".join("?" for _ in routine_ids)
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT routine_id, checked_date, completed
                    FROM routine_logs
                    WHERE checked_date IN ({", ".join("?" for _ in week_day_strs)})
                      AND routine_id IN ({placeholders})
                    """,
                    list(week_day_strs) + routine_ids,
                ).fetchall()
                for row in rows:
                    logs_map[(int(row["routine_id"]), row["checked_date"])] = int(row["completed"])

        # 각 루틴: 요일별(0/1/None) + 달성률
        matrix_rows = []
        for r in routines:
            days_status = []
            total_applicable = 0
            done_applicable = 0
            for i, d in enumerate(week_days):
                ds = d.strftime("%Y-%m-%d")
                if not self._routine_applies_on_date(r, d):
                    days_status.append(None)
                    continue
                total_applicable += 1
                completed = logs_map.get((r["id"], ds), 0)
                if completed == 1:
                    done_applicable += 1
                days_status.append(completed)
            completion_percent = 0
            if total_applicable > 0:
                completion_percent = round(done_applicable / total_applicable * 100)

            matrix_rows.append({
                "id": r["id"],
                "title": r["title"],
                "frequency": r["frequency"],
                "days_of_week": r.get("days_of_week"),
                "day_of_month": r.get("day_of_month"),
                "category": r.get("category"),
                "days": days_status,
                "completed_days": done_applicable,
                "total_days": total_applicable,
                "completion_percent": completion_percent,
            })

        # 요일별 달성률(우측 컬럼 역할)
        day_completion_rates: list[int] = []
        for i, d in enumerate(week_days):
            ds = d.strftime("%Y-%m-%d")
            applicable_count = 0
            done_count = 0
            for r in routines:
                if not self._routine_applies_on_date(r, d):
                    continue
                applicable_count += 1
                if logs_map.get((r["id"], ds), 0) == 1:
                    done_count += 1
            if applicable_count == 0:
                day_completion_rates.append(0)
            else:
                day_completion_rates.append(round(done_count / applicable_count * 100))

        return {
            "week_start": week_start,
            "week_days": week_day_strs,
            "routines": matrix_rows,
            "day_completion_rates": day_completion_rates,
        }
