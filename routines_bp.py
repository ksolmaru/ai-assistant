from flask import Blueprint, jsonify, request
from datetime import datetime, date, timedelta

from database import Database
from ai_agent import AIAssistant


db = Database()
routines_bp = Blueprint("routines_bp", __name__)

_assistant = None
_assistant_init_error = None


def _get_assistant():
    global _assistant, _assistant_init_error
    if _assistant is not None:
        return _assistant
    if _assistant_init_error is not None:
        raise ValueError(_assistant_init_error)

    try:
        _assistant = AIAssistant()
        return _assistant
    except Exception as e:
        _assistant_init_error = str(e)
        raise


def _parse_yyyy_mm_dd(value: str) -> str:
    d = datetime.strptime(value, "%Y-%m-%d").date()
    return d.strftime("%Y-%m-%d")


def _get_week_start(d: date) -> date:
    # Monday 기준
    return d - timedelta(days=d.weekday())


@routines_bp.route("/today", methods=["GET"])
def get_routines_today():
    try:
        checked_date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
        checked_date = _parse_yyyy_mm_dd(checked_date)
        routines = db.get_routines_for_date(checked_date)
        return jsonify({"date": checked_date, "routines": routines})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routines_bp.route("/weekly", methods=["GET"])
def get_routines_weekly():
    try:
        week_start = request.args.get("week_start")
        if not week_start:
            week_start = _get_week_start(date.today()).strftime("%Y-%m-%d")
        week_start = _parse_yyyy_mm_dd(week_start)
        matrix = db.get_routines_weekly_matrix(week_start)
        return jsonify(matrix)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routines_bp.route("/check", methods=["POST"])
def check_routine():
    try:
        data = request.get_json() or {}
        routine_id = int(data.get("routine_id"))
        checked_date = _parse_yyyy_mm_dd(data.get("date"))
        completed = int(data.get("completed", 0))
        note = data.get("note")

        db.set_routine_check(
            routine_id=routine_id,
            checked_date=checked_date,
            completed=completed,
            note=note,
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routines_bp.route("", methods=["GET"])
def list_routines():
    try:
        routines = db.get_routines(active_only=True)
        return jsonify({"routines": routines})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routines_bp.route("", methods=["POST"])
def create_routine():
    try:
        data = request.get_json() or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title is required"}), 400

        frequency = (data.get("frequency") or "daily").strip()
        if frequency not in {"daily", "weekly", "monthly"}:
            return jsonify({"error": "frequency must be 'daily'|'weekly'|'monthly'"}), 400

        days_of_week = data.get("days_of_week")
        day_of_month = data.get("day_of_month")
        category = data.get("category")
        active = int(data.get("active", 1))

        rid = db.add_routine(
            title=title,
            frequency=frequency,
            days_of_week=days_of_week,
            day_of_month=day_of_month,
            category=category,
            active=active,
        )
        return jsonify({"success": True, "routine_id": rid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routines_bp.route("/<int:routine_id>", methods=["PUT"])
def update_routine(routine_id: int):
    try:
        data = request.get_json() or {}
        allowed = {"title", "frequency", "days_of_week", "day_of_month", "category", "active"}
        kwargs = {k: v for k, v in data.items() if k in allowed}
        if not kwargs:
            return jsonify({"error": "no update fields"}), 400
        ok = db.update_routine(routine_id, **kwargs)
        if not ok:
            return jsonify({"error": "routine not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routines_bp.route("/<int:routine_id>", methods=["DELETE"])
def delete_routine(routine_id: int):
    try:
        ok = db.deactivate_routine(routine_id)
        if not ok:
            return jsonify({"error": "routine not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@routines_bp.route("/review", methods=["POST"])
def review_week():
    """
    Step 3에서 ai_agent.generate_routine_review()를 추가한 뒤,
    이 엔드포인트가 완전히 동작하도록 연동합니다.
    """
    try:
        data = request.get_json() or {}
        week_start = request.args.get("week_start") or data.get("week_start")
        if not week_start:
            week_start = _get_week_start(date.today()).strftime("%Y-%m-%d")
        week_start = _parse_yyyy_mm_dd(week_start)

        save = bool(data.get("save", False))

        matrix = db.get_routines_weekly_matrix(week_start)
        week_days = matrix.get("week_days", [])
        routine_summaries = [
            {
                "id": r["id"],
                "title": r["title"],
                "completed_days": r["completed_days"],
                "total_days": r["total_days"],
                "completion_percent": r["completion_percent"],
            }
            for r in matrix.get("routines", [])
        ]

        assistant = _get_assistant()
        if hasattr(assistant, "generate_routine_review"):
            review_text = assistant.generate_routine_review(
                routine_summaries=routine_summaries,
                week_days=week_days,
            )
        else:
            # Step 2 단계에서는 생성 함수가 없을 수 있으므로 일단 요약만 반환합니다.
            review_text = "AI 리뷰 기능은 아직 준비 중입니다. (Step 3 이후 동작)"

        # 저장: Step 3/6에서 UI가 save=true로 호출하도록 구성합니다.
        if save:
            review_date = week_days[-1] if week_days else week_start
            for r in routine_summaries:
                # completed는 임의 기준으로 결정(선택적 메모로 리뷰 저장 목적)
                completed = 1 if r["completion_percent"] >= 50 else 0
                db.set_routine_check(
                    routine_id=r["id"],
                    checked_date=review_date,
                    completed=completed,
                    note=str(review_text),
                )

        return jsonify({"success": True, "review": review_text, "week_start": week_start})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

