from __future__ import annotations

import json
from typing import Any, Callable

from .data_hub import KwangsungRepository


def nullable_string(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


class KwangsungToolRegistry:
    def __init__(self, repository: KwangsungRepository) -> None:
        self.repository = repository
        self._handlers: dict[str, Callable[..., Any]] = {
            "get_incoming_inspection": repository.get_incoming_inspection,
            "get_press_status": repository.get_press_status,
            "get_die_life": repository.get_die_life,
            "get_maintenance_risks": repository.get_maintenance_risks,
            "get_maintenance_history": repository.get_maintenance_history,
            "get_process_trace": repository.get_process_trace,
            "get_outgoing_inspection": repository.get_outgoing_inspection,
            "get_shipment_status": repository.get_shipment_status,
        }
        self._handlers.update({"search_knowledge": repository.search_knowledge, "get_rules": repository.get_rules, "get_table_inventory": repository.table_inventory, "get_table_records": repository.table_records})
        self.definitions = [
            self._tool("search_knowledge", "작업 절차·기준·승인·안전 문서를 검색한다.", {"query": {"type": "string"}}),
            self._tool("get_rules", "담당자 검토용 미승인 규칙을 조회한다.", {}),
            self._tool("get_table_inventory", "조회 가능한 DB 테이블과 건수를 확인한다.", {}),
            self._tool("get_table_records", "허용된 테이블을 읽기 전용 조회한다.", {"table": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "offset": {"type": "integer", "minimum": 0}}),
            self._tool("get_incoming_inspection", "입고 소재 LOT의 수입검사·성적서·보류 상태를 조회한다.", {
                "material_lot": nullable_string("소재 LOT. 전체이면 null"),
                "issues_only": {"type": "boolean", "description": "조건부합격·보류만 조회할지 여부"},
            }),
            self._tool("get_press_status", "프레스 압력·금형온도·스트로크·진동·전류 상태를 조회한다.", {
                "press_id": nullable_string("프레스 ID. 전체이면 null"),
            }),
            self._tool("get_die_life", "금형 정격·누적 스트로크와 명목 잔여수명을 조회한다.", {
                "die_id": nullable_string("금형 ID. 전체이면 null"),
            }),
            self._tool("get_maintenance_risks", "프레스·금형 예지보전 위험과 권고를 조회한다. 결과는 미검증 데모다.", {
                "press_id": nullable_string("프레스 ID. 전체이면 null"),
                "urgent_only": {"type": "boolean", "description": "높음·긴급만 조회할지 여부"},
            }),
            self._tool("get_maintenance_history", "설비·금형 정비와 다운타임 이력을 조회한다.", {
                "press_id": nullable_string("프레스 ID. 전체이면 null"),
                "die_id": nullable_string("금형 ID. 전체이면 null"),
            }),
            self._tool("get_process_trace", "작업지시를 입고검사부터 프레스·전착·마킹·출하검사까지 추적한다.", {
                "work_order": {"type": "string", "description": "작업지시번호"},
            }),
            self._tool("get_outgoing_inspection", "출하검사의 치수·외관·마킹·불량·승인 결과를 조회한다.", {
                "work_order": nullable_string("작업지시번호. 전체이면 null"),
                "issues_only": {"type": "boolean", "description": "합격 외 결과만 조회할지 여부"},
            }),
            self._tool("get_shipment_status", "작업지시별 출하예정·수량·품질승인을 조회한다.", {
                "work_order": nullable_string("작업지시번호. 전체이면 null"),
            }),
        ]

    @staticmethod
    def _tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False},
            "strict": True,
        }

    def execute(self, name: str, arguments: str | dict[str, Any]) -> str:
        if name not in self._handlers:
            return json.dumps({"error": "허용되지 않은 도구입니다.", "tool": name}, ensure_ascii=False)
        try:
            payload = json.loads(arguments) if isinstance(arguments, str) else arguments
            result = self._handlers[name](**payload)
            return json.dumps({"status": "ok", "demo_data": True, "result": result}, ensure_ascii=False, default=str)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return json.dumps({"error": str(exc), "tool": name}, ensure_ascii=False)
