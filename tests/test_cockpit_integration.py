import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from streamlit.testing.v1 import AppTest

from kwangsung_agent import KwangsungRepository, KwangsungToolRegistry, ManufacturingAgent
from kwangsung_agent.service import MAX_TOOL_ROUNDS


def test_documents_rules_and_persistence(tmp_path):
    path = tmp_path / 'demo.db'
    repo = KwangsungRepository(path)
    docs = repo.knowledge_documents()
    assert len(docs) == 10
    assert len(repo.get_rules()) == 7
    assert all(rule['source_document'] in {doc['document_id'] for doc in docs} for rule in repo.get_rules())
    assert repo.search_knowledge('프레스의 확인 절차')
    repo.save_setting('test', 'persisted')
    assert KwangsungRepository(path).setting('test') == 'persisted'
    assert len(repo.knowledge_documents()) == 10
    with pytest.raises(ValueError):
        repo.table_records('lots; DROP TABLE lots')


def test_snapshot_uses_matching_die_and_missing_prediction(tmp_path):
    from kwangsung_agent import work_order_snapshot, risk_label
    repo = KwangsungRepository(tmp_path / 'demo.db')
    snapshot = work_order_snapshot(repo, 'WO-260901')
    assert {r['die_id'] for r in snapshot['risks']} == {'DIE-101'}
    assert {r['die_id'] for r in snapshot['press']} == {'DIE-101'}
    with repo._connect() as connection:
        connection.execute("DELETE FROM maintenance_predictions WHERE die_id='DIE-101'")
    assert risk_label(work_order_snapshot(repo, 'WO-260901'))[0] == '미확인'
    assert risk_label(work_order_snapshot(repo, 'UNKNOWN'))[0] == '미확인'


def test_local_evidence_retained_and_hard_cap(tmp_path):
    registry = KwangsungToolRegistry(KwangsungRepository(tmp_path / 'demo.db'))
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        call = NS(type='function_call', name='search_knowledge', arguments='{"query":"금형"}', call_id=f'call_{len(requests)}')
        return NS(id=f'resp_{len(requests)}', output=[call], output_text='')
    answer = ManufacturingAgent(NS(responses=NS(create=create)), factory_tools=registry).ask('금형 기준은?')
    assert len(requests) == MAX_TOOL_ROUNDS + 1
    assert requests[-1]['tool_choice'] == 'none'
    assert answer.text and answer.evidence and answer.sources and answer.searched_documents
    assert answer.tool_rounds == MAX_TOOL_ROUNDS
    assert json.loads(registry.execute('get_rules', '{}'))['demo_data'] is True


def test_streamlit_render_and_controls(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "ui.db"))
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('POSTGRES_URL', '')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20).run()
    assert not app.exception
    for _ in range(2):
        next(b for b in app.button if b.label == '새 대화').click().run()
        assert not app.exception
    app.radio(key='recommendation_group').set_value('룰').run()
    assert app.session_state['question_group'] == '룰'
    app.selectbox(key='data_table').select('rules').run()
    app.text_input(key='document_query').set_value('금형').run()
    assert not app.exception
    assert app.session_state['previous_response_id'] is None
    assert len(app.session_state['messages']) == 1
    # Session settings can be reviewed without making network calls.
    next(t for t in app.text_input if t.label == '새 OpenAI API Key').set_value('fake-session-key')
    next(b for b in app.button if b.label == '설정 반영').click().run()
    assert app.session_state['agent_settings']['api_key'] == 'fake-session-key'
    assert not app.exception


def test_server_key_masking_and_restore(monkeypatch, tmp_path):
    monkeypatch.setenv('SQLITE_PATH', str(tmp_path / 'key-ui.db'))
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('POSTGRES_URL', '')
    monkeypatch.setenv('OPENAI_API_KEY', 'server-test-secret-abcd')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20).run()
    assert not app.exception
    field = next(t for t in app.text_input if t.label == '새 OpenAI API Key')
    assert field.value == ''
    assert all('server-test-secret' not in str(e.value) for e in app.success)
    app.session_state['previous_response_id'] = 'old-chain'
    field.set_value('session-test-secret')
    next(b for b in app.button if b.label == '설정 반영').click().run()
    assert app.session_state['previous_response_id'] is None
    app.run()
    next(b for b in app.button if b.label == '서버 기본 키 사용').click().run()
    assert app.session_state['agent_settings']['api_key'] == 'server-test-secret-abcd'
    assert not app.exception


def test_procedures_search_even_without_model_tool_call(tmp_path):
    registry = KwangsungToolRegistry(KwangsungRepository(tmp_path / 'procedure.db'))
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        return NS(id='response', output=[], output_text='담당자 확인이 필요합니다.\n근거: 검색 문서')
    answer = ManufacturingAgent(NS(responses=NS(create=create)), factory_tools=registry).ask('출하 승인 절차는?')
    assert answer.searched_documents and answer.evidence
    assert 'KWP-KB-008' in requests[0]['input']
