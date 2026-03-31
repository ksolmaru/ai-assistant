"""
app.py — Flask 웹 서버
브라우저에서 http://localhost:5000 으로 접속합니다.
"""
from flask import Flask, request, jsonify, render_template
from ai_agent import AIAssistant
from database import Database

app = Flask(__name__)
db = Database()

# 서버 시작 시점에 API 키가 없어도 웹앱은 구동되도록 지연 초기화합니다.
assistant = None
assistant_init_error = None


def get_assistant():
    """AIAssistant 인스턴스를 필요할 때 생성합니다."""
    global assistant, assistant_init_error
    if assistant is not None:
        return assistant
    if assistant_init_error is not None:
        raise ValueError(assistant_init_error)

    try:
        assistant = AIAssistant()
        return assistant
    except Exception as e:
        assistant_init_error = str(e)
        raise


@app.route("/")
def index():
    """메인 페이지 (채팅 UI)"""
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    """사용자 메시지를 받아 AI 응답을 반환합니다."""
    data = request.get_json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "메시지가 비어있습니다."}), 400

    try:
        response = get_assistant().chat(user_message)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks", methods=["GET"])
def get_tasks():
    """전체 할 일 목록을 반환합니다. status 쿼리 파라미터로 필터링 가능."""
    try:
        status = request.args.get("status")  # 없으면 전체 반환
        tasks = db.get_tasks(status=status)
        # 마감일 기준 정렬 (없는 것은 맨 뒤)
        tasks.sort(key=lambda t: (t["due_date"] or "9999-99-99", t["id"]))
        return jsonify({"tasks": tasks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks/new", methods=["POST"])
def create_task_direct():
    """UI 모달에서 직접 일정을 추가합니다 (AI 없이)."""
    try:
        data    = request.get_json()
        title   = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "제목을 입력해주세요."}), 400
        task_id = db.add_task(
            title       = title,
            description = data.get("description"),
            due_date    = data.get("due_date"),
            due_time    = data.get("due_time"),
            priority    = data.get("priority", "medium"),
            category    = data.get("category"),
            location    = data.get("location"),
            attendees   = data.get("attendees"),
        )
        # status가 todo가 아닌 경우 업데이트
        status = data.get("status", "todo")
        if status != "todo":
            db.update_task(task_id, status=status)
        return jsonify({"success": True, "task_id": task_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    """단일 할 일 상세 조회."""
    try:
        task = db.get_task_by_id(task_id)
        if not task:
            return jsonify({"error": "해당 일정을 찾을 수 없습니다."}), 404
        return jsonify({"task": task})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks/<int:task_id>", methods=["PATCH"])
def update_task(task_id):
    """일정 직접 수정 (UI에서 직접 편집 시 사용)."""
    try:
        data = request.get_json()
        allowed = {"title", "description", "status", "priority",
                   "due_date", "due_time", "category", "location", "attendees"}
        kwargs = {k: v for k, v in data.items() if k in allowed}
        success = db.update_task(task_id, **kwargs)
        if success:
            return jsonify({"success": True})
        return jsonify({"error": "해당 일정을 찾을 수 없습니다."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    """일정 삭제."""
    try:
        task = db.get_task_by_id(task_id)
        if not task:
            return jsonify({"error": "해당 일정을 찾을 수 없습니다."}), 404
        db.delete_task(task_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/greeting", methods=["GET"])
def greeting():
    """페이지 로드 시 오늘의 브리핑을 반환합니다."""
    try:
        response = get_assistant().get_greeting()
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/clear", methods=["POST"])
def clear_history():
    """대화 기록을 초기화합니다."""
    db.clear_conversations()
    return jsonify({"success": True, "message": "대화 기록이 초기화되었습니다."})


if __name__ == "__main__":
    print("=" * 50)
    print("  AI 비서 실행 중...")
    print("  브라우저에서 http://localhost:5000 접속")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)
