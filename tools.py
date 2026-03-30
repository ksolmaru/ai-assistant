"""
tools.py — Claude가 호출할 수 있는 도구(Tool) 정의
각 함수는 실제 DB 작업을 수행하고, TOOL_SCHEMAS는 Claude에게 전달할 스키마입니다.
"""
from datetime import datetime, timedelta
from database import Database

db = Database()


# ── 실제 실행 함수 ────────────────────────────────────────────────

def add_task(title, description=None, due_date=None, due_time=None,
             priority="medium", category=None, location=None, attendees=None):
    task_id = db.add_task(title, description, due_date, due_time, priority, category,
                          location, attendees)
    return {"success": True, "task_id": task_id, "message": f"'{title}' 일정이 추가되었습니다. (ID: {task_id})"}


def get_tasks(status=None, priority=None, category=None, due_before=None):
    tasks = db.get_tasks(status=status, priority=priority,
                         category=category, due_before=due_before)
    if not tasks:
        return {"tasks": [], "message": "조건에 맞는 할 일이 없습니다."}
    return {"tasks": tasks, "count": len(tasks)}


def update_task(task_id, title=None, description=None, status=None,
                priority=None, due_date=None, due_time=None, category=None,
                location=None, attendees=None):
    kwargs = {k: v for k, v in locals().items()
              if k != "task_id" and v is not None}
    success = db.update_task(task_id, **kwargs)
    if success:
        return {"success": True, "message": f"ID {task_id} 할 일이 수정되었습니다."}
    return {"success": False, "message": f"ID {task_id}를 찾을 수 없습니다."}


def complete_task(task_id):
    task = db.get_task_by_id(task_id)
    if not task:
        return {"success": False, "message": f"ID {task_id}를 찾을 수 없습니다."}
    db.update_task(task_id, status="done")
    return {"success": True, "message": f"'{task['title']}' 완료 처리되었습니다!"}


def delete_task(task_id):
    task = db.get_task_by_id(task_id)
    if not task:
        return {"success": False, "message": f"ID {task_id}를 찾을 수 없습니다."}
    db.delete_task(task_id)
    return {"success": True, "message": f"'{task['title']}' 삭제되었습니다."}


def get_upcoming_reminders(days_ahead=1):
    today = datetime.now().strftime("%Y-%m-%d")
    until = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    tasks = db.get_tasks(due_before=until)
    pending = [t for t in tasks if t["status"] != "done"]
    overdue = [t for t in pending if t["due_date"] and t["due_date"] < today]
    upcoming = [t for t in pending if t["due_date"] and today <= t["due_date"] <= until]
    return {
        "overdue": overdue,
        "upcoming": upcoming,
        "today": today,
        "message": f"기한 초과 {len(overdue)}건, 곧 마감 {len(upcoming)}건"
    }


# ── 함수 실행 라우터 ──────────────────────────────────────────────

TOOL_FUNCTIONS = {
    "add_task": add_task,
    "get_tasks": get_tasks,
    "update_task": update_task,
    "complete_task": complete_task,
    "delete_task": delete_task,
    "get_upcoming_reminders": get_upcoming_reminders,
}


def execute_tool(name, tool_input):
    """Claude가 요청한 tool을 실행하고 결과를 반환합니다."""
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return {"error": f"알 수 없는 도구: {name}"}
    try:
        return func(**tool_input)
    except Exception as e:
        return {"error": str(e)}


# ── Claude용 Tool 스키마 ──────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "add_task",
        "description": "새로운 할 일이나 일정을 추가합니다. 사용자가 무언가를 해야 한다고 말하면 이 도구를 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "할 일 제목 (간결하게)"
                },
                "description": {
                    "type": "string",
                    "description": "상세 설명 (선택사항)"
                },
                "due_date": {
                    "type": "string",
                    "description": "마감일 (YYYY-MM-DD 형식, 예: 2026-04-01). 오늘은 " + datetime.now().strftime("%Y-%m-%d") + "입니다."
                },
                "due_time": {
                    "type": "string",
                    "description": "마감 시간 (HH:MM 형식, 예: 14:00)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "우선순위: low(낮음), medium(보통), high(높음)"
                },
                "category": {
                    "type": "string",
                    "description": "카테고리 (예: 교회/찬양부, 공연팀, 부장님 보고/회의, 개인 약속 등)"
                },
                "location": {
                    "type": "string",
                    "description": "장소 (예: 본당, 2층 회의실, 강남역 카페)"
                },
                "attendees": {
                    "type": "string",
                    "description": "인원 정보. 숫자만 알면 'N명', 명단만 있으면 이름 나열, 둘 다면 'N명 (홍길동, 김철수)' 형식으로 작성"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "get_tasks",
        "description": "할 일 목록을 조회합니다. 필터 조건을 지정할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done"],
                    "description": "상태 필터: todo(할 일), in_progress(진행중), done(완료)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "우선순위 필터"
                },
                "category": {
                    "type": "string",
                    "description": "카테고리 필터"
                },
                "due_before": {
                    "type": "string",
                    "description": "이 날짜(YYYY-MM-DD) 이전 마감인 항목만 조회"
                }
            },
            "required": []
        }
    },
    {
        "name": "update_task",
        "description": "기존 할 일을 수정합니다. 마감일 변경, 우선순위 조정, 제목 수정 등에 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "수정할 할 일의 ID"
                },
                "title": {"type": "string", "description": "새 제목"},
                "description": {"type": "string", "description": "새 상세 설명"},
                "status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done"],
                    "description": "새 상태"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "새 우선순위"
                },
                "due_date": {"type": "string", "description": "새 마감일 (YYYY-MM-DD)"},
                "due_time": {"type": "string", "description": "새 마감 시간 (HH:MM)"},
                "category": {"type": "string", "description": "새 카테고리"},
                "location": {"type": "string", "description": "새 장소"},
                "attendees": {"type": "string", "description": "새 인원 정보 (예: '5명', '홍길동, 김철수', '5명 (홍길동, 김철수)')"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "complete_task",
        "description": "할 일을 완료 처리합니다. 사용자가 '다 했어', '완료', '끝냈어' 등의 말을 하면 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "완료할 할 일의 ID"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "delete_task",
        "description": "할 일을 삭제합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "삭제할 할 일의 ID"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "get_upcoming_reminders",
        "description": "마감이 임박하거나 기한이 지난 할 일을 조회합니다. 페이지 로드 시 또는 '뭐 놓친 거 있어?', '오늘 뭐 해야 해?' 등의 말에 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "몇 일 앞까지 조회할지 (기본값: 1)"
                }
            },
            "required": []
        }
    }
]
