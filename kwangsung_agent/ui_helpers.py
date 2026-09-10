from __future__ import annotations

from datetime import datetime
from typing import Any


QUESTION_GROUPS = {'지식베이스': ['공정추적 절차와 담당자를 알려줘', '수입검사 절차와 담당자를 알려줘', '프레스점검 절차와 담당자를 알려줘', '금형수명 절차와 담당자를 알려줘', '예지보전 절차와 담당자를 알려줘', '전착검사 절차와 담당자를 알려줘', '마킹추적 절차와 담당자를 알려줘', '출하승인 절차와 담당자를 알려줘', '프레스안전 절차와 담당자를 알려줘', '데이터검증 절차와 담당자를 알려줘'], 'DB': ['진행 작업지시를 보여줘', 'WO-260901을 입고부터 출하까지 추적해줘', 'PRS-01 설비 측정값을 보여줘', 'DIE-310 금형 잔여 스트로크를 알려줘', '정비 고위험 예측을 조회해줘', '수입검사 보류 소재를 보여줘', '출하검사 결과를 보여줘', '출하 승인대기 기록을 보여줘', 'PRS-01 정비 이력을 보여줘', 'DB 테이블과 저장 건수를 보여줘'], '룰': ['공정추적 검토 규칙과 근거 문서를 알려줘', '수입검사 검토 규칙과 근거 문서를 알려줘', '프레스점검 검토 규칙과 근거 문서를 알려줘', '금형수명 검토 규칙과 근거 문서를 알려줘', '예지보전 검토 규칙과 근거 문서를 알려줘', '전착검사 검토 규칙과 근거 문서를 알려줘', '마킹추적 검토 규칙과 근거 문서를 알려줘', '출하승인 검토 규칙과 근거 문서를 알려줘', '프레스안전 검토 규칙과 근거 문서를 알려줘', '데이터검증 검토 규칙과 근거 문서를 알려줘']}

WELCOME_MESSAGE = {"role": "assistant", "content": "안녕하세요. 광성정밀 제조 Agent입니다.  \n입고·수입검사부터 프레스·전착·마킹·출하검사까지 추적하고 설비·금형 예지보전 판단을 지원합니다.", "sources": [], "evidence": [], "data_tools": [], "created_at": "시작"}


def timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def user_question_history(messages: list[dict[str, Any]], limit: int = 8) -> list[dict[str, str]]:
    return [{"content": str(m.get("content", "")), "created_at": str(m.get("created_at", ""))} for m in reversed(messages) if m.get("role") == "user"][:limit]


def work_order_snapshot(repository: Any, work_order: str) -> dict[str, Any]:
    trace = repository.get_process_trace(work_order)
    job = trace.get("work_order") or {}
    press = repository.get_press_status(job.get("press_id")) if job else []
    die = repository.get_die_life(job.get("die_id")) if job else []
    risks = repository.get_maintenance_risks(job.get("press_id")) if job else []
    return {"job": job, "incoming": trace.get("incoming") or [], "processes": trace.get("processes") or [], "outgoing": trace.get("outgoing") or [], "shipments": trace.get("shipment") or [], "press": [r for r in press if r.get("die_id") == job.get("die_id")], "die": die, "risks": [r for r in risks if r.get("die_id") == job.get("die_id")]}


def risk_label(snapshot: dict[str, Any]) -> tuple[str, str]:
    if not snapshot.get("job") or not snapshot.get("risks"):
        return "미확인", "⚪"
    urgent = any(r.get("risk_level") in {"긴급", "높음"} for r in snapshot["risks"])
    hold = any(r.get("final_result") not in {"합격"} for r in snapshot["outgoing"])
    pending = any(r.get("status") == "승인대기" for r in snapshot["shipments"])
    incoming_hold = any(r.get("result") != "합격" for r in snapshot.get("incoming", []))
    score = int(urgent) * 2 + int(hold) + int(pending) + int(incoming_hold)
    return ("높음", "🔴") if score >= 3 else (("주의", "🟠") if score else ("안정", "🟢"))
