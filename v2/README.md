# 광성정밀 AI Agent V2

`new-agent-maker`의 2026-09-28 기준을 광성정밀 공정에 적용한 React 19 · TypeScript · Vite 7 · FastAPI 앱입니다. 기존 `kwangsung_agent` 저장소·도구·Responses 서비스를 재사용합니다. Streamlit V1과 기존 DB를 유지하고, 스킬 번들에서 실시간 음성 훅과 프런트 빌드 구성을 가져와 광성정밀에 맞게 수정했습니다.

## 실행

프로젝트 루트에서 실행합니다. Python 3.12, Node 22 이상을 사용합니다.

```bash
python3.12 -m venv .venv-v2
.venv-v2/bin/pip install -r v2/requirements.lock
npm ci --prefix v2/web
npm run build --prefix v2/web
.venv-v2/bin/uvicorn v2.api:app --host 127.0.0.1 --port 8514 --no-proxy-headers
```

접속: http://127.0.0.1:8514

이 작업 환경에서는 기존 `.venv`에 의존성을 설치했으므로 `.venv/bin/uvicorn`도 사용할 수 있습니다. 개발 중에는 API를 실행한 상태에서 `npm run dev --prefix v2/web`를 실행합니다. Vite는 `/api`를 8514로 프록시합니다.

## 구현한 흐름

- 왼쪽 지식베이스 검색·원문 모달, 읽기 전용 DB 테이블 및 페이지 조회
- 중앙 작업지시 / 소재 LOT 선택, 대화, 데모 조회·AI 분석, 새 대화, 실시간 음성
- 오른쪽 생산·품질 및 문서·규칙 추천질문 각 10개, 이 탭의 질의이력 최대 20개
- 모바일 자료·질문 패널, 직접 질문·추천질문·이력 재질문의 동일 처리 경로
- 이력 재질문 시 당시 작업지시 복원, LOT·모드 변경과 새 대화 시 이전 응답 취소 및 음성 정리
- 문서와 원본 레코드 근거, 조회시각·가상 데이터·미승인 상태 표시
- 같은 프레스의 다른 금형 기록을 구분하는 기존 작업지시 스냅샷 재사용
- WebRTC 실시간 음성, 자막, 발화 종료 감지·끼어들기, 음소거·종료, 연결 오류 시 마이크 해제
- 실제 광성정밀 읽기 전용 도구를 음성 세션에 연결하고 조회 근거를 대화에 표시

데모 모드는 키워드에 따른 저장 DB·문서 검색입니다. AI 분석이나 예측 모델 실행이 아닙니다. 등록된 수치·예지보전 점수는 2026년 9월의 가상 데이터이며 실제 제조 승인값으로 사용하지 않습니다. 설비 제어·출하 승인 도구는 없습니다.

## 서버 설정과 데이터

루트 `.env`를 읽습니다. `v2/.env.example`의 필요한 항목을 기존 설정에 병합하세요.

- `OPENAI_API_KEY`: 서버 전용. 브라우저에는 키를 전달하지 않습니다.
- `OPENAI_MODEL`: 미설정 또는 빈 값이면 기존 `DEFAULT_MODEL`을 사용합니다.
- `OPENAI_REALTIME_MODEL`, `OPENAI_REALTIME_VOICE`: 스킬 기준 모델·음성 설정을 유지합니다. 실제 계정 사용 가능 여부는 별도 확인이 필요합니다.
- `COCKPIT_ACCESS_TOKEN`: 외부 AI·음성 요청에 필요한 접근 코드. 브라우저는 sessionStorage에 저장합니다.
- `DATABASE_URL` 또는 `POSTGRES_URL`: 기존 PostgreSQL 어댑터를 실제로 사용합니다.
- `SQLITE_PATH`: 미설정 시 기존 `data/kwangsung_demo.db`를 사용합니다. 테스트는 임시 DB로 격리합니다.

로컬 AI 접근 예외는 서버가 요청 호스트와 실제 접속 주소를 모두 확인합니다. 프록시 헤더로 로컬 주소를 사칭하지 않도록 실행 명령에는 `--no-proxy-headers`를 사용합니다. 조회 API에는 조직별 로그인·권한 기능이 없으므로 기본 실행은 로컬 바인딩입니다. AI 접근 코드는 업무 데이터 접근 제어를 대신하지 않습니다. 외부 운영에는 별도 사용자 인증·TLS·접근 정책 연결이 필요합니다.

V1에서 저장한 `vector_store_id`가 있으면 V2 AI 분석에서도 File Search에 연결합니다. 문서 업로드·인덱싱 UI는 기존 V1에서 사용합니다. 새 대화는 브라우저 대화 문맥을 비우며, 서버는 별도 응답 체인을 저장하지 않습니다. 이력은 별도 ‘지우기’ 버튼으로 삭제합니다.

실시간 음성은 HTTPS 또는 localhost와 마이크 권한이 필요합니다. 연결은 [OpenAI WebRTC 공식 문서](https://developers.openai.com/api/docs/guides/voice-webrtc)의 서버 중계 방식을 사용합니다. 외부 센서 플랫폼 연결은 추가하지 않았습니다.

## 검증

```bash
.venv/bin/python -m pytest tests v2/tests -q
npm run build --prefix v2/web
# API 서버를 먼저 실행한 뒤:
cd v2/web
npx playwright install chromium
npm run test:e2e
```

이미 Chromium이 설치된 환경에서는 `PLAYWRIGHT_CHROMIUM_EXECUTABLE`에 실행파일 경로를 지정할 수 있습니다. 다른 포트는 `V2_TEST_URL`로 지정합니다. 브라우저 결과는 `v2/web/test-results/`에 저장되며 Git에 포함하지 않습니다.

2026-09-28 검증: Python 25개 통과, PostgreSQL 통합 테스트 1개는 관리자 URL 미설정으로 건너뜀. 프런트 빌드 및 브라우저 테스트 8개 통과. 데스크톱 1440px·모바일 390px에서 문서·테이블·질의·이력·LOT 변경·늦은 응답 차단을 확인했습니다. 음성 검증은 모의 WebRTC·서버 응답을 사용합니다. 실제 유료 AI·음성, 실기기 마이크, PostgreSQL 접속, Docker 빌드·구동은 실행하지 않았습니다.

## Docker 구성

로컬 호스트 8514에만 바인딩하며 SQLite를 named volume에 보존합니다. 기본 Docker DB는 별도 볼륨에 새로 생성되므로 로컬 V1 DB가 자동 복사되지 않습니다. Docker를 실제 구동한 결과는 아닙니다.

```bash
docker compose --env-file .env -f v2/docker-compose.yml config --quiet
docker compose --env-file .env -f v2/docker-compose.yml up -d --build
```

컨테이너 접속은 서버에서 루프백 주소로 인식되지 않을 수 있으므로 Docker에서 AI를 사용할 때는 `COCKPIT_ACCESS_TOKEN`을 설정하고 화면 설정에 입력하세요. PostgreSQL은 기존 어댑터를 사용하지만 V2 Compose 자체에 DB 컨테이너를 새로 추가하지 않습니다.
