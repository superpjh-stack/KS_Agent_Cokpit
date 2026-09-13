from __future__ import annotations

import os
import hashlib
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from kwangsung_agent.voice import VoiceService
from openai import OpenAI

from kwangsung_agent import (
    DEFAULT_MODEL, MAX_RETRIES, REQUEST_TIMEOUT_SECONDS, QUESTION_GROUPS, WELCOME_MESSAGE,
    create_repository, KwangsungToolRegistry,
    ManufacturingAgent, timestamp, user_question_history, work_order_snapshot, risk_label,
)


load_dotenv(Path(__file__).parent / ".env")
BASE_DIR = Path(__file__).parent
SERVER_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

st.set_page_config(page_title="광성정밀 Agent Cockpit", page_icon="⚙️", layout="wide", initial_sidebar_state="collapsed")
st.markdown(f"<style>{(BASE_DIR / 'assets' / 'cockpit.css').read_text()}</style>", unsafe_allow_html=True)

repository = create_repository(os.getenv("SQLITE_PATH", str(BASE_DIR / "data" / "kwangsung_demo.db")))
registry = KwangsungToolRegistry(repository)

for key, default in {
    "messages": [WELCOME_MESSAGE.copy()], "vector_store_id": repository.setting("vector_store_id"), "uploaded_names": [],
    "previous_response_id": None, "pending_question": None, "question_group": "지식베이스",
    "voice_draft": "", "voice_digest": None, "mobile_voice_digest": None,
    "mobile_voice_reply_pending": False,
    "agent_settings": {"api_key": SERVER_API_KEY,
                       "model": (os.getenv("OPENAI_MODEL") or DEFAULT_MODEL), "max_results": 6},
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Preserve active sessions when recommendation categories change.
if st.session_state.question_group not in QUESTION_GROUPS:
    st.session_state.question_group = next(iter(QUESTION_GROUPS))

with st.sidebar:
    st.header("Agent 설정")
    settings = st.session_state.agent_settings
    key_status = st.empty()
    with st.expander("API 키·모델 변경", expanded=not bool(settings["api_key"])):
        st.caption("변경할 때만 입력하세요. 빈 키 입력란은 현재 적용된 키를 유지합니다.")
        with st.form("agent_settings_form", clear_on_submit=True):
            draft_api_key = st.text_input("새 OpenAI API Key", type="password")
            draft_model = st.text_input("모델", value=settings["model"])
            draft_max_results = st.slider("문서 검색 결과", 1, 20, settings["max_results"])
            apply_settings = st.form_submit_button("설정 반영", type="primary", use_container_width=True)
        st.caption("여기서 입력한 키는 현재 세션에 적용됩니다. 서버 기본 키는 Hostinger의 OPENAI_API_KEY 환경변수에서 변경합니다.")
        if SERVER_API_KEY and settings["api_key"] != SERVER_API_KEY:
            if st.button("서버 기본 키 사용", use_container_width=True):
                st.session_state.agent_settings = {**settings, "api_key": SERVER_API_KEY}
                st.session_state.previous_response_id = None
                st.rerun()
    if apply_settings:
        if not draft_model.strip():
            st.error("모델 이름을 입력해 주세요. 기존 설정은 유지됩니다.")
        else:
            next_api_key = draft_api_key.strip() or settings["api_key"]
            if next_api_key != settings["api_key"]:
                st.session_state.previous_response_id = None
            settings = {"api_key": next_api_key, "model": draft_model.strip(),
                        "max_results": draft_max_results}
            st.session_state.agent_settings = settings
            st.success("설정을 반영했습니다.")
    api_key, model, max_results = settings["api_key"], settings["model"], settings["max_results"]
    if api_key:
        masked_key = "••••••••" + (api_key[-4:] if len(api_key) > 8 else "")
        source = "서버 기본 키 · 자동 적용" if api_key == SERVER_API_KEY else "변경한 키 · 현재 세션"
        key_status.success(f"{source}\n\n현재 키: {masked_key}")
    else:
        key_status.info("서버 기본 키가 없습니다. 아래에서 API 키를 입력해 주세요.")
    if SERVER_API_KEY:
        st.caption("새로 접속해도 서버 기본 키가 자동 적용됩니다.")
    st.divider()
    st.subheader("지식문서")
    uploads = st.file_uploader("설비·금형·검사·안전 SOP 문서", accept_multiple_files=True, type=["pdf", "docx", "txt", "md", "csv"])
    upload_agent = ManufacturingAgent(OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES), model=model, factory_tools=registry) if api_key else None
    if st.button("문서 인덱싱", use_container_width=True, disabled=not uploads or not upload_agent):
        try:
            if not st.session_state.vector_store_id:
                st.session_state.vector_store_id = upload_agent.create_knowledge_base()
                repository.save_setting("vector_store_id", st.session_state.vector_store_id)
            for uploaded in uploads:
                temp_path: str | None = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as temp:
                        temp.write(uploaded.getbuffer())
                        temp_path = temp.name
                    indexed_file = upload_agent.add_file(st.session_state.vector_store_id, temp_path)
                    if indexed_file.status != "completed":
                        raise RuntimeError(f"{uploaded.name}: 문서 인덱싱 미완료 ({indexed_file.status})")
                    content = uploaded.getvalue().decode("utf-8", errors="replace") if Path(uploaded.name).suffix.lower() in {".txt", ".md", ".csv"} else None
                    repository.save_uploaded_document(indexed_file.id, uploaded.name, content)
                    if uploaded.name not in st.session_state.uploaded_names:
                        st.session_state.uploaded_names.append(uploaded.name)
                finally:
                    if temp_path:
                        Path(temp_path).unlink(missing_ok=True)
            st.success(f"{len(uploads)}개 문서 연결 완료")
        except Exception as exc:
            st.error("문서 인덱싱에 실패했습니다. API 연결과 파일 형식을 확인해 주세요.")
    st.caption(f"저장된 지식문서: {len(repository.knowledge_documents())}개 (로컬 샘플 포함)")
    st.divider()
    st.caption("데모 데이터·예측은 실제 운영값이 아닙니다. 설비정지·금형교체·품질·출하는 담당자가 승인합니다.")

agent = ManufacturingAgent(OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES), model=model, factory_tools=registry) if api_key else None
voice_service = VoiceService(agent.client) if agent else None


def submit_voice_question():
    text = st.session_state.voice_draft.strip()
    if text:
        st.session_state.pending_question = text
        st.session_state.voice_draft = ""
        st.session_state.voice_digest = None


kpi = repository.dashboard()

st.markdown("""
<header class="factory-header">
  <div><div class="brand-line">KWANGSUNG PRECISION / MANUFACTURING</div>
  <h1>광성정밀 AI Agent</h1>
  <p>입고부터 출하까지, 작업지시와 설비·금형 근거를 연결합니다.</p></div>
  <div class="header-meta"><strong>생산관리 워크스페이스</strong><span>검증용 데모 데이터</span></div>
</header>
<div class="process-strip"><b>제조 공정</b><span>입고·수입검사</span><i>→</i><span>프레스</span><i>→</i><span>전착</span><i>→</i><span>마킹</span><i>→</i><span>출하검사</span></div>
<div class="overview-label"><strong>현장 주요 지표</strong><span>작업지시 / 예지보전 / 품질 · 2026-09 샘플</span></div>
""", unsafe_allow_html=True)

with st.container(key="kpis"):
    metrics = st.columns(5)
    metrics[0].metric("진행 작업", f"{kpi['active_work_orders']}건")
    metrics[1].metric("프레스 경고", f"{kpi['press_alerts']}건")
    metrics[2].metric("정비 고위험", f"{kpi['maintenance_risks']}건")
    metrics[3].metric("수입검사 이슈", f"{kpi['incoming_holds']}건")
    metrics[4].metric("출하 대기", f"{kpi['shipment_pending']}건")

with st.container(key="mobile_navigation"):
    st.markdown('''<nav class="mobile-nav" aria-label="모바일 업무 메뉴">
    <a href="#agent-chat" target="_self">대화</a>
    <a href="#knowledge-data" target="_self">지식·데이터</a>
    <a href="#work-questions" target="_self">업무 질문</a>
    </nav>''', unsafe_allow_html=True)

with st.container(key="workspace"):
    left_col, chat_col, context_col = st.columns([1.1, 2.6, 1.3], gap="medium")

with left_col:
    st.markdown('<div id="work-questions" class="mobile-anchor"></div>', unsafe_allow_html=True)
    with st.container(border=True, key="history_panel"):
        st.markdown("#### 대화 이력")
        if st.button("새 대화", use_container_width=True):
            st.session_state.messages = [WELCOME_MESSAGE.copy()]
            st.session_state.previous_response_id = None
            st.session_state.pending_question = None
            st.session_state.voice_draft = ""
            st.session_state.voice_digest = None
            st.session_state.mobile_voice_digest = None
            st.session_state.mobile_voice_reply_pending = False
            st.rerun()
        history = user_question_history(st.session_state.messages)
        if not history:
            st.caption("아직 질문이 없습니다.")
        for index, item in enumerate(history):
            label = item["content"] if len(item["content"]) <= 38 else item["content"][:38] + "…"
            if st.button(label, key=f"history_{index}", use_container_width=True, help=item["created_at"]):
                st.session_state.pending_question = item["content"]
                st.rerun()

    with st.container(border=True, key="suggestions_panel"):
        st.markdown("#### 추천 질문")
        st.caption("지식베이스 10개 · DB 10개 · 룰 10개")
        group = st.radio("조회 영역", list(QUESTION_GROUPS), index=list(QUESTION_GROUPS).index(st.session_state.question_group), horizontal=True, key="recommendation_group", label_visibility="collapsed")
        if group:
            st.session_state.question_group = group
        st.caption(f"{st.session_state.question_group} 조회 질문 10개")
        for index, suggestion in enumerate(QUESTION_GROUPS[st.session_state.question_group]):
            if st.button(f"{index + 1:02d}. {suggestion}", key=f"suggestion_{st.session_state.question_group}_{index}", use_container_width=True):
                st.session_state.pending_question = suggestion
                st.rerun()
        st.markdown('<div class="tiny-note">추천질문은 선택 즉시 채팅으로 전달됩니다. 실행·승인이 필요한 업무는 Agent가 담당자를 안내합니다.</div>', unsafe_allow_html=True)

with context_col:
    st.markdown('<div id="knowledge-data" class="mobile-anchor"></div>', unsafe_allow_html=True)
    with st.container(border=True, key="context"):
        st.markdown('<div class="section-eyebrow">KNOWLEDGE & DATA</div>', unsafe_allow_html=True)
        st.markdown("#### 지식·데이터 현황")
        inventory = repository.table_inventory()
        data_tables = [item for item in inventory if item["table"] != "rules" and item["exists"]]
        rule_table = next(item for item in inventory if item["table"] == "rules")
        documents = repository.knowledge_documents()
        summary = st.columns(3)
        summary[0].metric("연결 문서", f"{len(documents)}개")
        summary[1].metric("DB 데이터", f"{sum(item['count'] for item in data_tables)}건")
        summary[2].metric("등록 룰", f"{rule_table['count']}건")

        with st.expander("작업지시 상황·공정 확인"):
            lot_id = st.selectbox("조회 작업지시", [row["work_order"] for row in repository.get_work_orders()])
            snap = work_order_snapshot(repository, lot_id)
            label, icon = risk_label(snap)
            st.write(f"{icon} {label} · {snap['job'].get('item_name', '')}")
            st.caption(f"소재 {snap['job'].get('material_lot', '미확인')} · 설비 {snap['job'].get('press_id', '미확인')} · 금형 {snap['job'].get('die_id', '미확인')}")
            for heading, rows in [("공정 이력", snap["processes"]), ("설비 측정", snap["press"]), ("금형 상태", snap["die"]), ("예지보전 예측", snap["risks"]), ("수입검사", snap["incoming"]), ("출하검사", snap["outgoing"]), ("출하 승인", snap["shipments"])]:
                st.markdown(f"**{heading}**")
                if rows:
                    st.dataframe(rows, hide_index=True)
                else:
                    st.caption("미확인 · 연결 기록이 없습니다.")
            st.caption("작업지시에 소재 LOT·설비·금형·검사·출하 이력을 연결합니다. 측정과 예측은 미검증 데모입니다.")
            if st.button("이 작업지시 브리핑", key="lot_brief", use_container_width=True):
                st.session_state.pending_question = f"{lot_id}의 입고·프레스·금형·검사·출하 확인사항을 브리핑해줘"
                st.rerun()

        st.markdown("##### RAG 지식문서")
        st.caption("저장된 샘플·업로드 문서 / 세션 종료 후에도 유지")
        if documents:
            query = st.text_input("문서 검색", placeholder="예: 프레스, 금형, 수입검사", key="document_query")
            filtered = [doc for doc in documents if not query.strip() or query.strip().lower() in
                        (doc["filename"] + " " + (doc["content"] or "")).lower()]
            st.caption(f"전체 {len(documents)}개 / 검색 결과 {len(filtered)}개")
            if filtered:
                doc_ids = [doc["document_id"] for doc in filtered]
                by_id = {doc["document_id"]: doc for doc in filtered}
                selected_doc = st.selectbox("조회할 문서", doc_ids,
                    format_func=lambda doc_id: by_id[doc_id]["filename"], key="selected_document")
                doc = by_id[selected_doc]
                st.caption(f"{doc['source']} / {doc['status']}")
                with st.expander("문서 본문 보기", expanded=True):
                    if doc["content"]:
                        with st.container(height=240):
                            st.text(doc["content"])
                    else:
                        st.caption("로컬 본문 미보관 문서입니다. AI 대화에서 File Search로 검색할 수 있습니다.")
                if doc["content"]:
                    st.download_button("문서 내려받기", data=doc["content"], file_name=doc["filename"],
                                       mime="text/plain", key="download_knowledge")
            else:
                st.info("검색어에 해당하는 문서가 없습니다.")
        else:
            st.info("등록된 지식문서가 없습니다.")
        st.caption("로컬 샘플은 키워드 검색으로 대화에 연결됩니다. 실제 승인 문서가 아닌 검증용 예시입니다.")
        with st.expander(f"등록 룰 바로 보기 · {rule_table['count']}건"):
            for rule in repository.get_rules():
                st.write(f"**{rule['rule_id']} | {rule['name']}**")
                st.text(f"조건: {rule['condition']}\n담당: {rule['owner']}\n조치: {rule['action']}\n근거: {rule['source_document']} / {rule['revision']}")
            st.caption("등록된 조건을 조회하는 기능이며 설비·업무를 자동 실행하지 않습니다.")

        st.divider()
        st.markdown("##### 룰·공정 데이터")
        if not rule_table["exists"]:
            st.caption("판정 룰: 미등록 (룰 테이블 없음)")
        elif not rule_table["count"]:
            st.caption("판정 룰: 테이블은 있으나 등록된 규칙이 없습니다.")
        with st.expander(f"테이블별 저장 현황 · {len(data_tables)}개 업무 테이블"):
            st.dataframe([
                {"구분": item["label"], "저장 건수": item["count"],
                 "상태": "등록" if item["exists"] else "미등록"}
                for item in inventory
            ], hide_index=True, use_container_width=True)
        table_names = [item["table"] for item in inventory]
        selected_table = st.selectbox(
            "조회할 데이터", table_names,
            format_func=lambda name: repository.TABLE_LABELS[name], key="data_table",
        )
        selected_info = next(item for item in inventory if item["table"] == selected_table)
        page_count = max(1, (selected_info["count"] + 49) // 50)
        page = st.selectbox("페이지", range(1, page_count + 1), key=f"data_page_{selected_table}") if page_count > 1 else 1
        records = repository.table_records(selected_table, offset=(page - 1) * 50)
        st.caption(f"{selected_info['label']} 전체 {selected_info['count']}건 / 현재 {len(records)}건")
        if records:
            with st.expander("저장 데이터 보기", expanded=True):
                st.dataframe(records, hide_index=True, use_container_width=True, height=210)
                st.caption("표를 좌우로 움직여 모든 항목을 확인할 수 있습니다.")
            with st.expander("레코드 상세 조회"):
                record_index = st.selectbox(
                    "레코드", range(len(records)),
                    format_func=lambda index: str(next(iter(records[index].values()))),
                    key=f"data_record_{selected_table}_{page}",
                )
                st.json(records[record_index], expanded=True)
        else:
            st.info("저장된 데이터가 없습니다.")
        st.caption("DB는 검증용 가상 데이터입니다. 이 패널에서는 조회만 가능합니다.")

with chat_col:
    st.markdown('<div id="agent-chat" class="mobile-anchor"></div>', unsafe_allow_html=True)
    with st.container(border=True, height=580, key="chat_panel"):
        st.markdown('''<div class="chat-shell-header">
          <div><div class="chat-shell-kicker">MANUFACTURING ASSISTANT</div><strong>현장 AI 상담</strong>
          <span>작업지시·설비·금형·출하를 한 곳에서 확인합니다.</span></div>
          <div class="chat-shell-status"><i></i> 데모 Data Hub</div>
        </div>''', unsafe_allow_html=True)
        if not user_question_history(st.session_state.messages):
            st.markdown('''<div class="chat-intro"><h2>소재 입고부터 출하까지,<br>현장의 판단을 빠르게.</h2>
            <p>설비 위험, 금형 수명, 검사 보류을 질문하세요.<br>LOT 데이터와 기준서를 연결해 확인합니다.</p></div>''', unsafe_allow_html=True)
        if not agent:
            st.info("API 키를 설정하면 자연어 대화를 시작할 수 있습니다. 추천질문과 지식·데이터 현황은 미리 볼 수 있습니다.")
        for message_index, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"] == "assistant" and message.get("created_at") != "시작":
                    if st.button("음성으로 듣기", key=f"speak_{message_index}", disabled=voice_service is None):
                        try:
                            if not message.get("audio"):
                                with st.spinner("답변을 음성으로 만들고 있습니다…"):
                                    message["audio"] = voice_service.speak(message["content"])
                        except Exception:
                            st.error("음성을 만들지 못했습니다. API 연결·사용 한도를 확인하고 다시 눌러주세요.")
                    if message.get("audio"):
                        autoplay_audio = bool(message.pop("autoplay_audio", False))
                        if autoplay_audio:
                            st.caption("답변을 자동으로 재생합니다. 필요하면 재생 버튼으로 다시 들으세요.")
                        else:
                            st.caption("AI가 생성한 음성입니다. 재생 버튼을 누르면 들을 수 있습니다.")
                        st.audio(message["audio"], format="audio/mpeg", autoplay=autoplay_audio)
                if message.get("data_tools") or message.get("evidence") or message.get("sources") or "searched_documents" in message:
                    with st.expander("근거 자세히 보기"):
                        grounds = []
                        if message.get("data_tools"):
                            grounds.append("Data Hub: " + ", ".join(message["data_tools"]))
                        searched_files = list(dict.fromkeys(
                            [row.get("filename", "문서") for row in message.get("evidence", [])] + list(message.get("sources", []))
                        ))
                        if searched_files:
                            grounds.append("문서: " + ", ".join(searched_files))
                        if grounds:
                            st.caption("근거 · " + " · ".join(grounds))
                        if "searched_documents" in message:
                            if not message["searched_documents"]:
                                note = ("지식문서를 검색하지 않고 Data Hub 조회만으로 답했습니다."
                                        if message.get("knowledge_base_connected")
                                        else "지식문서가 연결되지 않아 Data Hub 조회만으로 답했습니다.")
                                st.caption(f"⚠️ {note} 사내 규정·판정기준은 원문으로 확인하세요.")
                        if message.get("evidence"):
                            for evidence in message["evidence"]:
                                score = evidence.get("score")
                                score_text = f" · 유사도 {score:.3f}" if isinstance(score, (int, float)) else ""
                                st.markdown(f"**{evidence['filename']}**{score_text}")
                                st.write(evidence.get("text") or "검색 텍스트 미제공")
    with st.container(key="mobile_voice_bar"):
        mobile_voice_hint = (
            "마이크를 누르고 말한 뒤 정지하면 자동으로 질문합니다."
            if voice_service
            else "음성 질문을 사용하려면 왼쪽 상단에서 API 키를 먼저 설정하세요."
        )
        st.markdown(
            f'<div class="mobile-voice-guide"><strong>음성 질문</strong><span>{mobile_voice_hint}</span></div>',
            unsafe_allow_html=True,
        )
        mobile_recording = st.audio_input(
            "음성으로 바로 질문",
            key="mobile_voice_recording",
            help="마이크를 누르고 질문하세요. 녹음을 마치면 질문 전송과 답변 음성 재생이 자동으로 이어집니다.",
            disabled=voice_service is None,
            label_visibility="collapsed",
            width="stretch",
        )
        mobile_digest = hashlib.sha256(mobile_recording.getvalue()).hexdigest() if mobile_recording else None
        if mobile_recording and mobile_digest != st.session_state.mobile_voice_digest:
            st.session_state.mobile_voice_digest = mobile_digest
            try:
                with st.spinner("질문을 듣고 있습니다…"):
                    mobile_question = voice_service.transcribe(mobile_recording.getvalue())
                st.session_state.pending_question = mobile_question
                st.session_state.mobile_voice_reply_pending = True
                st.toast(f"음성 질문: {mobile_question}", icon="🎙️")
                st.rerun()
            except ValueError as exc:
                st.session_state.mobile_voice_reply_pending = False
                st.toast(str(exc), icon="⚠️")
            except Exception:
                st.session_state.mobile_voice_reply_pending = False
                st.toast("음성 인식에 실패했습니다. API 연결·사용 한도를 확인해 주세요.", icon="⚠️")
    with st.container(border=True, key="voice_panel"):
        st.markdown("##### 음성으로 질문하기")
        st.caption("녹음 → 글자로 변환 → 확인 후 질문 보내기")
        recording = st.audio_input("마이크로 질문 녹음", key="voice_recording", disabled=voice_service is None)
        digest = hashlib.sha256(recording.getvalue()).hexdigest() if recording else None
        if digest != st.session_state.voice_digest:
            st.session_state.voice_digest = digest
            st.session_state.voice_draft = ""
        if st.button("녹음한 질문을 글자로 변환", key="transcribe_voice", disabled=not recording or voice_service is None):
            try:
                with st.spinner("질문을 듣고 있습니다…"):
                    st.session_state.voice_draft = voice_service.transcribe(recording.getvalue())
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("음성 인식에 실패했습니다. API 연결·사용 한도를 확인한 뒤 다시 시도하거나 글로 질문하세요.")
        if st.session_state.voice_draft:
            st.text_area("인식한 질문 (수정 가능)", key="voice_draft", height=90)
            st.button("이 질문 보내기", key="send_voice", type="primary", on_click=submit_voice_question,
                      disabled=not st.session_state.voice_draft.strip() or voice_service is None)
        st.caption("변환할 때 녹음이 OpenAI로 전송됩니다. 마이크 사용을 허용해 주세요. 녹음은 DB에 저장하지 않습니다.")
        if not voice_service:
            st.caption("왼쪽 상단 설정에서 API 키를 입력하면 음성 기능을 사용할 수 있습니다.")
    typed_question = st.chat_input("설비·금형·작업지시·검사·출하에 질문하세요", disabled=agent is None)

if typed_question:
    st.session_state.pending_question = typed_question
question = st.session_state.pop("pending_question", None)
if question:
    if not agent:
        st.toast("질문을 실행하려면 API 키를 먼저 설정하세요.", icon="🔑")
    else:
        st.session_state.messages.append({"role": "user", "content": question, "created_at": timestamp()})
        auto_voice_reply = bool(st.session_state.pop("mobile_voice_reply_pending", False))
        try:
            answer = agent.ask(question, st.session_state.vector_store_id, st.session_state.previous_response_id, max_results)
            assistant_message = {
                "role": "assistant", "content": answer.text, "sources": answer.sources,
                "evidence": answer.evidence, "data_tools": answer.data_tools, "created_at": timestamp(),
                "searched_documents": answer.searched_documents,
                "knowledge_base_connected": answer.knowledge_base_connected,
            }
            if auto_voice_reply:
                try:
                    with st.spinner("답변을 음성으로 만들고 있습니다…"):
                        assistant_message["audio"] = voice_service.speak(answer.text)
                    assistant_message["autoplay_audio"] = True
                except Exception:
                    st.toast("답변은 완료됐지만 음성 재생을 준비하지 못했습니다.", icon="⚠️")
            st.session_state.messages.append(assistant_message)
            st.session_state.previous_response_id = answer.response_id
        except Exception as exc:
            st.session_state.messages.append({"role": "assistant", "content": "답변 생성에 실패했습니다. API 연결·모델 설정·사용 한도를 확인해 주세요.", "created_at": timestamp()})
        st.rerun()

st.markdown('<footer class="workspace-footer">광성정밀 제조 업무 지원 | 표시된 수치와 예측은 검증용 가상 데이터입니다.</footer>', unsafe_allow_html=True)
