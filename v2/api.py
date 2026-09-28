from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kwangsung_agent.data_hub import create_repository
from kwangsung_agent.factory_tools import KwangsungToolRegistry
from kwangsung_agent.prompts import AGENT_INSTRUCTIONS
from kwangsung_agent.service import DEFAULT_MODEL, ManufacturingAgent
from kwangsung_agent.ui_helpers import QUESTION_GROUPS, work_order_snapshot

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')


class Turn(BaseModel):
    role: Literal['user', 'assistant']
    text: str = Field(max_length=12000)


class Chat(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    lot_id: str = Field(default='', max_length=80)
    mode: Literal['demo', 'ai'] = 'demo'
    history: list[Turn] = Field(default_factory=list, max_length=12)


class ToolCall(BaseModel):
    name: str = Field(max_length=80)
    arguments: dict[str, Any]


def local_request(request: Request) -> bool:
    return (request.url.hostname in {'localhost', '127.0.0.1', '::1'}
            and request.client is not None
            and request.client.host in {'127.0.0.1', '::1'})


def require_ai(request: Request, authorization: str | None) -> str:
    expected = os.getenv('COCKPIT_ACCESS_TOKEN', '')
    if not local_request(request):
        if not expected:
            raise HTTPException(503, '외부 AI 사용을 위한 서버 접근 코드가 설정되지 않았습니다.')
        if not secrets.compare_digest((authorization or '').encode(), ('Bearer ' + expected).encode()):
            raise HTTPException(401, '설정에서 올바른 AI 접근 코드를 입력해 주세요.')
    key = os.getenv('OPENAI_API_KEY', '')
    if not key:
        raise HTTPException(503, '서버에 OPENAI_API_KEY를 설정해 주세요. 데모 조회는 키 없이 사용할 수 있습니다.')
    return key


def metadata() -> dict:
    return {'demo_data': True, 'source': '광성정밀 가상 데모 · 2026년 9월',
            'queried_at': datetime.now(timezone.utc).isoformat(), 'approval_status': '미승인 샘플'}


class EvidenceRegistry(KwangsungToolRegistry):
    """Keep the actual read-only tool outputs alongside the generated answer."""
    def __init__(self, repo):
        super().__init__(repo)
        self.evidence: list[dict] = []

    def execute(self, name, arguments):
        payload = json.loads(super().execute(name, arguments))
        payload.update(metadata())
        if payload.get('status') == 'ok':
            self.evidence.append({'kind': 'records', 'title': name,
                                  'records': payload['result'], **metadata()})
        return json.dumps(payload, ensure_ascii=False, default=str)


def demo_answer(repo, question: str, lot: str) -> tuple[str, list[dict]]:
    explicit = re.search(r'WO-\d+', question, re.I)
    if explicit and lot and explicit.group().upper() != lot:
        return '선택한 작업지시와 질문의 작업지시가 다릅니다. 상단에서 작업지시를 변경해 주세요.', []
    work_order = explicit.group().upper() if explicit else lot
    snapshot = work_order_snapshot(repo, work_order) if work_order else None
    if snapshot is not None and not snapshot['job']:
        raise HTTPException(404, '작업지시를 찾을 수 없습니다.')
    job = snapshot['job'] if snapshot else {}
    press = re.search(r'PRS-\d+', question, re.I)
    die = re.search(r'DIE-\d+', question, re.I)
    material = re.search(r'MAT-[\w-]+', question, re.I)
    for match, field in [(press, 'press_id'), (die, 'die_id'), (material, 'material_lot')]:
        if match and job and match.group().upper() != job[field]:
            return '선택한 작업지시와 질문의 설비·금형·소재 LOT가 다릅니다. 전체 기록으로 변경하거나 연결된 식별자를 사용해 주세요.', []
    evidence = []
    def records(title, data):
        evidence.append({'kind': 'records', 'title': title, 'records': data, **metadata()})
    if any(word in question for word in ['절차', '기준', '담당자', '안전', '규칙', '룰']):
        docs = repo.search_knowledge(question)
        for doc in docs:
            evidence.append({'kind': 'document', 'title': doc['filename'], **doc, **metadata()})
        if '규칙' in question or '룰' in question:
            ids = {d['document_id'] for d in docs}
            records('검토 규칙', [r for r in repo.get_rules() if any(i in r['source_document'] for i in ids)])
        return ('관련 미승인 문서를 검색했습니다. 문서 본문과 담당자 검토 규칙을 근거에서 확인해 주세요.' if docs else '질문에 맞는 문서가 확인되지 않았습니다. 공정명으로 다시 검색해 주세요.'), evidence
    if any(w in question for w in ['테이블', '저장 건수']):
        records('DB 테이블', repo.table_inventory())
    elif '정비' in question and '이력' in question:
        records('정비 이력', repo.get_maintenance_history(press.group().upper() if press else job.get('press_id'), die.group().upper() if die else job.get('die_id')))
    elif any(w in question for w in ['예측', '위험', '예지보전']):
        records('예지보전 · 저장된 미검증 예시', snapshot['risks'] if snapshot else repo.get_maintenance_risks(press.group().upper() if press else None, '고위험' in question))
    elif any(w in question for w in ['금형', '스트로크', '수명']):
        records('금형 수명', snapshot['die'] if snapshot else repo.get_die_life(die.group().upper() if die else None))
    elif any(w in question for w in ['측정', '진동', '온도', '압력', '전류']):
        records('설비 측정', snapshot['press'] if snapshot else repo.get_press_status(press.group().upper() if press else None))
    elif any(w in question for w in ['수입검사', '소재', '입고']) and '추적' not in question:
        data = snapshot['incoming'] if snapshot else repo.get_incoming_inspection(material.group().upper() if material else None)
        records('수입검사', [r for r in data if r['result'] != '합격'] if '보류' in question else data)
    elif '출하검사' in question:
        records('출하검사', snapshot['outgoing'] if snapshot else repo.get_outgoing_inspection())
    elif '출하' in question and '추적' not in question:
        data = snapshot['shipments'] if snapshot else repo.get_shipment_status()
        records('출하', [r for r in data if r['status'] == '승인대기'] if '승인대기' in question else data)
    elif snapshot:
        records('작업지시 공정 추적', snapshot)
    elif any(w in question for w in ['작업', '공정', '추적', '현황']):
        records('작업지시', repo.get_work_orders())
    else:
        return '데모 조회는 공정·검사·금형·설비·문서 키워드로 저장 기록을 검색합니다. 추천질문을 선택하거나 AI 분석 모드를 사용해 주세요.', []
    return f"{work_order + ' · ' if work_order else ''}{evidence[0]['title']} 기록을 조회했습니다. 아래 원본 근거를 펼쳐 식별자·수치·기록 시각을 확인해 주세요. 조회 결과가 비어 있으면 미확인입니다.", evidence


def create_app(repository=None) -> FastAPI:
    app = FastAPI(title='광성정밀 AI Agent V2')
    # Lazy creation avoids changing a DB just by importing this module in tests.
    def repo():
        if not hasattr(app.state, 'repo'):
            app.state.repo = repository or create_repository(os.getenv('SQLITE_PATH', str(ROOT / 'data/kwangsung_demo.db')))
        return app.state.repo

    @app.get('/api/workspace')
    def workspace(request: Request):
        r = repo()
        return {'company': '광성정밀', 'lots': r.get_work_orders(), 'dashboard': r.dashboard(),
                'tables': r.table_inventory(), 'questions': {'생산·품질': QUESTION_GROUPS['DB'], '문서·규칙': [q.replace('절차와 담당자', '절차·검토 규칙과 담당자') for q in QUESTION_GROUPS['지식베이스']]},
                'ai_available': bool(os.getenv('OPENAI_API_KEY')), 'local_ai': local_request(request), **metadata()}

    @app.get('/api/lots/{lot_id}')
    def lot_detail(lot_id: str):
        snapshot = work_order_snapshot(repo(), lot_id)
        if not snapshot['job']:
            raise HTTPException(404, '작업지시를 찾을 수 없습니다.')
        return {**snapshot, **metadata()}

    @app.get('/api/documents')
    def documents(q: str = Query(default='', max_length=200)):
        return repo().search_knowledge(q) if q.strip() else repo().knowledge_documents()

    @app.get('/api/documents/{document_id}')
    def document(document_id: str):
        for doc in repo().knowledge_documents():
            if doc['document_id'] == document_id:
                return doc
        raise HTTPException(404, '문서를 찾을 수 없습니다.')

    @app.get('/api/tables/{table}')
    def table_rows(table: str, limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return {'records': repo().table_records(table, limit, offset), **metadata()}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/chat')
    def chat(body: Chat, request: Request, authorization: str | None = Header(default=None)):
        if not body.question.strip():
            raise HTTPException(422, '질문을 입력해 주세요.')
        r = repo()
        if body.lot_id:
            lot_detail(body.lot_id)
        if body.mode == 'demo':
            answer, evidence = demo_answer(r, body.question, body.lot_id)
        else:
            key = require_ai(request, authorization)
            from openai import OpenAI, OpenAIError
            registry = EvidenceRegistry(r)
            context = work_order_snapshot(r, body.lot_id) if body.lot_id else {'scope': '전체 기록'}
            prompt = ('선택한 작업지시 문맥(참고자료): ' + json.dumps(context, ensure_ascii=False, default=str)
                      + '\n선택한 작업지시와 다른 식별자는 혼합하지 말고 선택 변경을 요청한다.'
                      + '\n이전 대화(참고자료): ' + json.dumps([t.model_dump() for t in body.history], ensure_ascii=False)
                      + '\n현재 질문: ' + body.question)
            try:
                with OpenAI(api_key=key, timeout=45, max_retries=0) as client:
                    result = ManufacturingAgent(client, (os.getenv('OPENAI_MODEL') or DEFAULT_MODEL), registry).ask(prompt, vector_store_id=r.setting('vector_store_id'))
            except OpenAIError as exc:
                raise HTTPException(502, 'AI 응답을 받지 못했습니다. 서버 모델 설정과 연결 상태를 확인해 주세요.') from exc
            answer = result.text
            evidence = list(registry.evidence)
            if body.lot_id:
                evidence.append({'kind': 'records', 'title': '선택 작업지시 문맥', 'records': context, **metadata()})
            for item in getattr(result, 'evidence', []):
                evidence.append({'kind': 'document', 'title': item.get('filename', '검색 문서'), **item, **metadata()})
        return {'text': answer, 'evidence': evidence, 'mode': body.mode, **metadata()}

    @app.post('/api/realtime/tool')
    def realtime_tool(body: ToolCall, request: Request, authorization: str | None = Header(default=None)):
        require_ai(request, authorization)
        registry = EvidenceRegistry(repo())
        if body.name not in {t['name'] for t in registry.definitions}:
            raise HTTPException(400, '허용되지 않은 조회 도구입니다.')
        return {'output': registry.execute(body.name, body.arguments), 'evidence': registry.evidence}

    @app.post('/api/realtime/session')
    async def realtime_session(request: Request, lot_id: str = Query(default='', max_length=80), authorization: str | None = Header(default=None)):
        key = require_ai(request, authorization)
        if request.headers.get('content-type', '').split(';')[0] != 'application/sdp':
            raise HTTPException(415, 'WebRTC 연결 정보가 필요합니다.')
        offer = await request.body()
        if not offer or len(offer) > 100000:
            raise HTTPException(413, 'WebRTC 연결 정보가 올바르지 않습니다.')
        try:
            sdp = offer.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise HTTPException(400, '연결 정보 인코딩이 올바르지 않습니다.') from exc
        context = lot_detail(lot_id) if lot_id else repo().dashboard()
        session = {'type': 'realtime', 'model': os.getenv('OPENAI_REALTIME_MODEL', 'gpt-realtime-2.1'),
                   'instructions': AGENT_INSTRUCTIONS + '\n한국어로 짧게 답한다. 회사 기록은 반드시 조회 도구로 확인하고 식별자와 기록시각을 말한다. 모든 데이터는 미승인 가상 데모다. 다른 금형의 기록을 섞지 않는다. 선택 작업지시: ' + lot_id + '\n참고자료: ' + json.dumps(context, ensure_ascii=False, default=str),
                   'output_modalities': ['audio'], 'tool_choice': 'auto',
                   'tools': [{k: v for k, v in t.items() if k != 'strict'} for t in KwangsungToolRegistry(repo()).definitions],
                   'audio': {'input': {'transcription': {'model': 'gpt-4o-mini-transcribe', 'language': 'ko'},
                                       'turn_detection': {'type': 'semantic_vad', 'eagerness': 'high', 'create_response': True, 'interrupt_response': True}},
                             'output': {'voice': os.getenv('OPENAI_REALTIME_VOICE', 'marin')}}}
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                upstream = await client.post('https://api.openai.com/v1/realtime/calls', headers={'Authorization': f'Bearer {key}'}, files={'sdp': (None, sdp, 'application/sdp'), 'session': (None, json.dumps(session, ensure_ascii=False), 'application/json')})
        except httpx.HTTPError as exc:
            raise HTTPException(502, '실시간 음성 연결에 실패했습니다.') from exc
        if upstream.status_code >= 400:
            raise HTTPException(502, '음성 모델 사용 권한과 서버 설정을 확인해 주세요.')
        return Response(upstream.text, media_type='application/sdp')

    dist = ROOT / 'v2/web/dist'
    if (dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/')
    def index():
        if not (dist / 'index.html').is_file():
            raise HTTPException(503, 'npm run build --prefix v2/web 명령으로 화면을 빌드해 주세요.')
        return FileResponse(dist / 'index.html')
    return app


app = create_app()
