import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from kwangsung_agent.data_hub import KwangsungRepository
from v2.api import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', '')
    return TestClient(create_app(KwangsungRepository(tmp_path / 'demo.db')))


def test_workspace_and_readonly_sources(client):
    workspace = client.get('/api/workspace').json()
    assert len(workspace['lots']) == 3
    assert [len(q) for q in workspace['questions'].values()] == [10, 10]
    assert workspace['demo_data'] and not workspace['ai_available']
    docs = client.get('/api/documents?q=금형').json()
    assert docs and '금형' in docs[0]['text']
    assert client.get('/api/documents/' + docs[0]['document_id']).json()['content']
    assert client.get('/api/documents/missing').status_code == 404
    assert client.get('/api/tables/app_settings').status_code == 400
    assert client.get('/api/tables/work_orders?limit=101').status_code == 422
    first = client.get('/api/tables/work_orders?limit=1').json()['records']
    second = client.get('/api/tables/work_orders?limit=1&offset=1').json()['records']
    assert first[0]['work_order'] != second[0]['work_order']


def test_selected_work_order_separates_dies(client):
    response = client.post('/api/chat', json={'question': '설비 측정값', 'lot_id': 'WO-260901'}).json()
    assert {r['die_id'] for r in response['evidence'][0]['records']} == {'DIE-101'}
    other = client.post('/api/chat', json={'question': '설비 측정값', 'lot_id': 'WO-260903'}).json()
    assert {r['die_id'] for r in other['evidence'][0]['records']} == {'DIE-310'}
    mismatch = client.post('/api/chat', json={'question': 'DIE-310 금형 잔여 수명', 'lot_id': 'WO-260901'}).json()
    assert not mismatch['evidence'] and '다릅니다' in mismatch['text']
    assert client.post('/api/chat', json={'question': '현황', 'lot_id': 'UNKNOWN'}).status_code == 404


def test_all_suggestions_are_supported(client):
    groups = client.get('/api/workspace').json()['questions']
    for question in sum(groups.values(), []):
        response = client.post('/api/chat', json={'question': question})
        assert response.status_code == 200
        body = response.json()
        assert body['evidence'], question
        assert body['demo_data'] and body['mode'] == 'demo'
        assert all(e['queried_at'] and e['approval_status'] == '미승인 샘플' for e in body['evidence'])


def test_validation_and_no_invented_answer(client):
    assert client.post('/api/chat', json={'question': '  '}).status_code == 422
    assert client.post('/api/chat', json={'question': 'x' * 2001}).status_code == 422
    unknown = client.post('/api/chat', json={'question': '점심 메뉴'}).json()
    assert not unknown['evidence'] and '데모 조회' in unknown['text']
    assert client.post('/api/chat', json={'question': '현황', 'mode': 'ai'}).status_code == 503


def test_external_auth_cannot_be_bypassed_with_host(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-not-real-key')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'example-access')
    body = {'question': '현황', 'mode': 'ai'}
    assert client.post('/api/chat', json=body, headers={'host': 'localhost'}).status_code == 401
    assert client.post('/api/chat', json=body, headers={'Authorization': 'Bearer wrong'}).status_code == 401
    workspace = client.get('/api/workspace').text
    assert 'test-not-real-key' not in workspace and 'example-access' not in workspace


def test_ai_evidence_and_history_are_request_scoped(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-not-real-key')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'example-access')
    seen = []
    def fake_ask(self, question, **kwargs):
        seen.append(question)
        self.factory_tools.execute('get_die_life', {'die_id': 'DIE-101'})
        return SimpleNamespace(text='금형 조회 결과입니다.')
    monkeypatch.setattr('v2.api.ManufacturingAgent.ask', fake_ask)
    headers = {'Authorization': 'Bearer example-access'}
    first = client.post('/api/chat', json={'question': '금형 조회', 'lot_id': 'WO-260901', 'mode': 'ai', 'history': [{'role': 'user', 'text': '이전질문표식'}]}, headers=headers)
    assert first.status_code == 200
    assert first.json()['evidence'][0]['records'][0]['die_id'] == 'DIE-101'
    second = client.post('/api/chat', json={'question': '금형 조회', 'mode': 'ai'}, headers=headers)
    assert second.status_code == 200
    assert '이전질문표식' in seen[0] and '이전질문표식' not in seen[1]


def test_realtime_tools_are_real_readonly_handlers(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-not-real-key')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'example-access')
    headers = {'Authorization': 'Bearer example-access'}
    result = client.post('/api/realtime/tool', json={'name': 'get_die_life', 'arguments': {'die_id': 'DIE-310'}}, headers=headers)
    assert result.status_code == 200
    assert json.loads(result.json()['output'])['result'][0]['die_id'] == 'DIE-310'
    assert result.json()['evidence']
    assert client.post('/api/realtime/tool', json={'name': 'stop_press', 'arguments': {}}, headers=headers).status_code == 400
    assert client.post('/api/realtime/session', content='sdp', headers=headers).status_code == 415


def test_realtime_sdp_and_tools_config(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-not-real-key')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'example-access')
    captured = {}
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(status_code=200, text='v=0\r\nanswer')
    monkeypatch.setattr('v2.api.httpx.AsyncClient', FakeClient)
    response = client.post('/api/realtime/session?lot_id=WO-260901', content='v=0\r\noffer', headers={'Content-Type': 'application/sdp', 'Authorization': 'Bearer example-access'})
    assert response.status_code == 200 and response.text == 'v=0\r\nanswer'
    session = json.loads(captured['files']['session'][1])
    assert 'WO-260901' in session['instructions']
    assert any(t['name'] == 'get_press_status' for t in session['tools'])
    assert session['audio']['input']['turn_detection']['interrupt_response']
    assert all(t['type'] == 'function' for t in session['tools'])
