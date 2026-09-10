from __future__ import annotations

from typing import Any


def extract_sources(response: Any) -> list[str]:
    """응답 주석에서 모델이 실제로 인용한 문서 파일명을 추출한다."""
    sources: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                filename = getattr(annotation, "filename", None)
                if filename and filename not in sources:
                    sources.append(filename)
    return sources


def extract_evidence(response: Any) -> list[dict[str, Any]]:
    """file_search 호출이 반환한 검색 스니펫을 추출한다."""
    evidence: list[dict[str, Any]] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "file_search_call":
            continue
        for result in getattr(item, "results", []) or []:
            evidence.append({
                "filename": getattr(result, "filename", None) or "문서",
                "text": getattr(result, "text", None),
                "score": getattr(result, "score", None),
            })
    return evidence


def searched_documents(response: Any) -> bool:
    """이 응답에서 문서 검색이 실제로 실행됐는지 확인한다."""
    return any(getattr(item, "type", None) == "file_search_call" for item in getattr(response, "output", []) or [])


def merge_sources(accumulated: list[str], response: Any) -> list[str]:
    """도구 호출 라운드마다 인용 문서를 누적한다. 마지막 응답만 보면 앞 라운드 근거가 사라진다."""
    for filename in extract_sources(response):
        if filename not in accumulated:
            accumulated.append(filename)
    return accumulated


def merge_evidence(accumulated: list[dict[str, Any]], response: Any) -> list[dict[str, Any]]:
    """라운드별 검색 스니펫을 파일명·본문 기준으로 중복 없이 누적한다."""
    seen = {(row.get("filename"), row.get("text")) for row in accumulated}
    for row in extract_evidence(response):
        key = (row.get("filename"), row.get("text"))
        if key in seen:
            continue
        seen.add(key)
        accumulated.append(row)
    return accumulated
