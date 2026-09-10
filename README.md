# 광성정밀 제조 AI Agent Cockpit · V1

임진강김치 V1 화면과 `agent-cokpit-maker`·`skill-1-streamlit` 스킬을 광성정밀의 제조 공정에 적용한 **Streamlit 앱**입니다.

입고·수입검사 → 프레스 → 전착 → 마킹 → 출하검사를 작업지시·소재 LOT로 연결하고, 설비·금형 예지보전과 현장 지식검색을 지원합니다.

## 구현 기능

- 진행 작업·설비 경고·정비 위험·수입검사·출하 KPI
- 중앙 대화, 대화 이력, 지식베이스·DB·룰 추천질문 각 10개
- 작업지시별 공정·설비 측정·금형·예측·입고/출하검사·승인 기록
- 전용 샘플 문서 10개, 문서에 연결된 검토 규칙 7개
- 문서 검색·본문·내려받기와 읽기 전용 DB 테이블·페이지·레코드 조회
- 여러 도구 호출에서 문서 근거 유지, 도구 반복 상한 및 빈 응답 대체 안내
- 서버 API 키 자동 적용·마스킹, 세션별 변경 및 서버 기본 키 복귀
- 음성 입력 → 변환 → 수정 → 전송, 답변 음성 재생
- 모바일 대화 우선 화면, PostgreSQL + pgvector 연결과 SQLite 데모

모든 품목·식별자·측정값·예측·거래처는 **2026년 9월 가상 데모**입니다. 문서와 규칙은 미승인 예시입니다. 위험점수는 실제 학습·추론 결과가 아닌 저장된 예시이며 제품 불량 확률이 아닙니다. 정지·정비·금형교체·품질·출하 결정은 담당자가 승인합니다.

## 로컬 실행

Python 3.11 이상:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env
streamlit run app.py --server.port 8504
```

브라우저에서 `http://localhost:8504`에 접속합니다. API 키 없이도 작업지시·문서·DB·규칙을 조회할 수 있습니다. 자연어 대화·문서 인덱싱·음성 기능에는 `.env`의 `OPENAI_API_KEY`가 필요합니다.

기본 모델은 `kwangsung_agent/service.py`의 `DEFAULT_MODEL` 한 곳에서 관리합니다. 기존 프로젝트의 모델 설정을 유지했으며, 실제 계정에서 사용할 수 있는 모델은 `OPENAI_MODEL` 또는 화면 설정으로 지정하세요. API 키의 전체 값은 입력란에 표시하지 않습니다. 빈 키 입력은 기존 값을 유지하고, 키 변경 시 이전 대화 연결을 초기화합니다.

`DATABASE_URL`이 있으면 PostgreSQL을 사용합니다. 없으면 `data/kwangsung_demo.db` SQLite 데모를 사용합니다. `SQLITE_PATH`로 별도 데모 경로를 지정할 수 있습니다. 샘플 문서와 규칙은 첫 초기화 시 저장되며 기존 저장 문서는 덮어쓰지 않습니다.

## Docker 실행

`.env`에서 `POSTGRES_PASSWORD`를 URL에 안전한 긴 영숫자 비밀번호로 지정합니다.

```bash
docker compose config --quiet
docker compose up -d --build
```

앱은 호스트 8504 포트, DB는 외부 포트 없이 독립 named volume을 사용합니다. PostgreSQL 17 + pgvector가 정상 상태가 된 뒤 앱이 시작됩니다. 첫 시작에 vector 확장·스키마·샘플·1536차원 벡터 열·HNSW 인덱스를 초기화합니다.

문서 키워드 검색은 API 없이 작동합니다. 로컬 문서의 임베딩 생성은 자동 실행하지 않습니다. 벡터 검색은 `save_uploaded_document(..., embedding=...)`와 `vector_search_knowledge()`로 제공하며 화면의 업로드 인덱싱은 OpenAI File Search를 사용합니다.

`.env`와 키는 이미지에 포함하지 않습니다. 배포 서버의 `.env` 또는 Docker Manager 환경변수에서 `OPENAI_API_KEY`를 변경한 뒤 앱 컨테이너를 재생성합니다.

```bash
docker compose up -d --force-recreate app
```

## SQLite → PostgreSQL 이전

원본 앱을 한 번 실행해 문서·규칙을 초기화한 뒤 이전합니다. 기본 동작은 **대상 업무 데이터·문서·규칙·설정 전체 교체**입니다. 대상 DB를 백업하고 점검 시간에 실행하세요. 한 트랜잭션에서 처리하며 실패 시 롤백하고 반복 실행해도 중복되지 않습니다.

```bash
DATABASE_URL='postgresql://user:password@localhost:5432/kwp_cockpit' \
  python scripts/migrate_sqlite_to_postgres.py --source data/kwangsung_demo.db
```

기존 행을 보존하면서 누락된 기본키만 추가하려면 `--append`를 사용합니다.

## 검증

```bash
python -m pytest -q
python -m compileall -q app.py kwangsung_agent scripts
```

SQLite 데이터·문서/규칙 지속성·금형별 근거 분리·예측 누락·도구 상한·문서 근거·Streamlit 렌더링·대화 초기화·추천 그룹·테이블/문서 변경·API 키 마스킹/복귀를 검사합니다.

PostgreSQL 초기화·벡터 검색·반복 이전 테스트는 별도 테스트 서버의 `TEST_POSTGRES_ADMIN_URL`을 지정하면 임시 DB를 생성·삭제하여 실행합니다. 지정하지 않으면 건너뜁니다. 실제 AI 호출·마이크·음성 재생은 키와 장치가 있는 환경에서 확인해야 합니다.

### 이번 환경의 확인 결과

자동 테스트 12개 통과, PostgreSQL 테스트 1개는 관리자 URL 미설정으로 건너뛰었습니다. 데스크톱 및 모바일 390px 화면을 확인했으며 페이지 가로 넘침과 브라우저 오류가 없었습니다. Docker CLI가 없어 Compose 및 실제 컨테이너 구동은 검증하지 못했습니다. 실제 AI·음성 호출은 API 키 없이 검증하지 않았습니다.

브라우저 자동 번역이 켜져 있으면 이미 한국어인 용어를 잘못 바꿀 수 있습니다. 화면 문구가 어색하면 원문 보기로 확인하세요.
