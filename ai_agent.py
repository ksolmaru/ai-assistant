"""
ai_agent.py — Claude API 연동 + Tool Use 루프
사용자 메시지를 받아 Claude와 대화하고, 필요 시 DB 도구를 호출합니다.
"""
import json
import os
from datetime import datetime

import anthropic
from anthropic import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError
from dotenv import load_dotenv

from database import Database
from tools import TOOL_SCHEMAS, execute_tool

load_dotenv()

# 개인 비서 역할을 정의하는 시스템 프롬프트
SYSTEM_PROMPT = f"""당신은 친근하고 유능한 개인 비서입니다. 사용자의 업무와 일정을 관리해줍니다.

오늘 날짜: {{today}}

## 역할
- 사용자가 해야 할 일을 자연어로 말하면 할 일 목록에 추가합니다
- 마감이 임박하거나 놓친 일이 있으면 먼저 알려줍니다
- 할 일 조회, 수정, 완료, 삭제를 자연스럽게 처리합니다
- 사용자가 루틴(매일/매주/매월 체크)을 말하면 루틴 정의를 추가/수정하고, 오늘 체크/해제를 `routine_logs`에 반영합니다
- 사용자가 루틴 달성 현황(오늘/이번 주)을 물으면 이를 조회해 간단히 요약해줍니다
- 우선순위를 파악해서 중요한 일을 먼저 안내합니다

## 일정 저장 규칙
일정을 추가할 때는 아래 항목을 자연어에서 파악해서 저장하세요:
- title: 일정 제목
- due_date / due_time: 날짜와 시간
- category: 교회/찬양부, 공연팀, 부장님 보고/회의, 개인 약속 중 해당하는 것 선택
- location: 언급된 장소
- attendees: 인원 정보 — 숫자만 알면 "N명", 명단만 있으면 이름 나열, 둘 다면 "N명 (홍길동, 김철수)" 형식
- description: 그 외 메모나 추가 정보

## 일정 표시 형식
일정을 보여줄 때는 아래 형식으로 보여주세요 (없는 항목은 생략):

📅 날짜(요일) 시간
제목: [제목]
장소: [location]
인원: [attendees]
메모: [description]

## 대화 스타일
- 친근하고 따뜻한 말투를 사용합니다 (반말 또는 존댓말, 사용자에 맞춤)
- 간결하게 답변합니다 (긴 설명보다 핵심만)
- 할 일이 추가/수정되면 결과를 명확히 확인해줍니다
- 여러 할 일이 있을 때는 목록 형태로 보여줍니다

## 날짜 파싱 규칙
- "내일" → 내일 날짜 (YYYY-MM-DD)
- "이번 주 금요일" → 해당 날짜
- "다음 주" → 다음 주 월요일
- "오늘" → 오늘 날짜
"""


class AIAssistant:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다.\n"
                ".env 파일에 ANTHROPIC_API_KEY=sk-ant-... 를 추가해주세요."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.db = Database()

    def _get_system_prompt(self):
        return SYSTEM_PROMPT.replace("{today}", datetime.now().strftime("%Y년 %m월 %d일 (%A)"))

    def chat(self, user_message: str) -> str:
        """사용자 메시지를 처리하고 AI 응답을 반환합니다."""
        # 대화 기록 저장 (DB 오류가 나도 대화는 계속)
        try:
            self.db.add_message("user", user_message)
        except Exception as e:
            print(f"[DB 경고] 메시지 저장 실패: {e}")

        # 최근 20개 대화 기록 불러오기 (맥락 유지)
        try:
            history = self.db.get_recent_messages(limit=20)
        except Exception as e:
            print(f"[DB 경고] 대화 기록 불러오기 실패: {e}")
            history = [{"role": "user", "content": user_message}]

        # Tool Use 루프: Claude가 도구 호출을 멈출 때까지 반복
        messages = history[:]
        final_response = ""

        try:
            while True:
                response = self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4096,
                    system=self._get_system_prompt(),
                    tools=TOOL_SCHEMAS,
                    messages=messages
                )

                # 도구 호출이 없으면 최종 응답 추출 후 종료
                if response.stop_reason == "end_turn":
                    final_response = next(
                        (block.text for block in response.content if block.type == "text"),
                        ""
                    )
                    break

                # 도구 호출 처리
                if response.stop_reason == "tool_use":
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            result = execute_tool(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False)
                            })

                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                else:
                    final_response = "죄송합니다, 처리 중 오류가 발생했습니다."
                    break

        except AuthenticationError:
            return "API 키가 올바르지 않습니다. .env 파일의 ANTHROPIC_API_KEY를 확인해주세요."
        except RateLimitError:
            return "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
        except APIStatusError as e:
            if e.status_code == 529:
                return "Anthropic 서버가 일시적으로 과부하 상태입니다. 잠시 후 다시 시도해주세요."
            return f"API 오류가 발생했습니다 (상태 코드: {e.status_code}). 잠시 후 다시 시도해주세요."
        except APIConnectionError:
            return "Anthropic 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."
        except Exception as e:
            return f"처리 중 예상치 못한 오류가 발생했습니다: {str(e)}"

        # 최종 응답 저장 (DB 오류가 나도 응답은 반환)
        if final_response:
            try:
                self.db.add_message("assistant", final_response)
            except Exception as e:
                print(f"[DB 경고] 응답 저장 실패: {e}")

        return final_response

    def generate_routine_review(self, routine_summaries: list[dict], week_days: list[str]) -> str:
        """
        주간 루틴 달성 결과를 바탕으로 AI 리뷰를 생성합니다.
        - routine_summaries: [{title, completed_days, total_days, completion_percent}, ...]
        - week_days: [YYYY-MM-DD, ...] (월~일)
        """
        # 전체 달성률(루틴 평균) 계산
        percent_values = [
            int(r.get("completion_percent", 0))
            for r in routine_summaries
            if int(r.get("total_days", 0)) > 0
        ]
        overall_percent = round(sum(percent_values) / len(percent_values)) if percent_values else 0

        lines = []
        for r in routine_summaries:
            title = r.get("title", "")
            done = r.get("completed_days", 0)
            total = r.get("total_days", 0)
            pct = r.get("completion_percent", 0)
            if total and total > 0:
                lines.append(f"- {title}: {done}/{total}일 완료 ({pct}%)")
            else:
                lines.append(f"- {title}: 이번 주 대상 없음")

        start = week_days[0] if week_days else ""
        end = week_days[-1] if week_days else ""

        review_prompt = f"""
너는 루틴 관리 비서입니다. 아래는 {start}~{end} 기간의 주간 루틴 달성 현황입니다.

## 루틴 달성 현황
{chr(10).join(lines)}

## 평가 기준
- 각 루틴의 달성률이 80% 이상이면 칭찬
- 50~79%면 중립
- 50% 미만이면 신랄하지만 도움이 되게 피드백
- 전체 달성률(루틴 평균)이 30% 미만이면 전체적으로 매우 직설적으로 평가

## 출력 요구
- 루틴별로 1~3문장씩 간단히 코멘트
- 다음 주 개선 포인트 1~2개를 제안
- 말투는 친근하지만 할 말은 하는 비서 스타일로 작성
""".strip()

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                system="당신은 친절하고 실행을 돕는 루틴 리뷰어입니다.",
                messages=[{"role": "user", "content": review_prompt}],
            )
            return next((block.text for block in response.content if block.type == "text"), "")
        except AuthenticationError:
            return "API 키가 올바르지 않습니다. .env 파일의 ANTHROPIC_API_KEY를 확인해주세요."
        except RateLimitError:
            return "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
        except APIStatusError as e:
            if e.status_code == 529:
                return "Anthropic 서버가 일시적으로 과부하 상태입니다. 잠시 후 다시 시도해주세요."
            return f"API 오류가 발생했습니다 (상태 코드: {e.status_code}). 잠시 후 다시 시도해주세요."
        except APIConnectionError:
            return "Anthropic 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."
        except Exception as e:
            return f"루틴 리뷰 생성 중 예상치 못한 오류가 발생했습니다: {str(e)}"

    def get_greeting(self) -> str:
        """페이지 로드 시 오늘의 브리핑을 생성합니다."""
        today = datetime.now().strftime("%Y-%m-%d")
        greeting_prompt = f"오늘은 {today}이야. 간단히 인사하고, 오늘 할 일과 마감 임박한 것들을 알려줘."
        return self.chat(greeting_prompt)
