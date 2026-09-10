from __future__ import annotations

import sqlite3
import os
import re
import json
from pathlib import Path
from typing import Any


class KwangsungRepository:
    """광성정밀 프로토타입용 SQLite Data Hub. 모든 레코드는 가상 데모 데이터다."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS work_orders (
          work_order TEXT PRIMARY KEY, item_code TEXT, item_name TEXT, order_qty INTEGER,
          material_lot TEXT, press_id TEXT, die_id TEXT, due_date TEXT, status TEXT, progress_pct REAL
        );
        CREATE TABLE IF NOT EXISTS incoming_inspections (
          inspection_id TEXT PRIMARY KEY, material_lot TEXT, supplier TEXT, material_spec TEXT,
          received_qty INTEGER, thickness_mm REAL, hardness_hrb REAL, result TEXT,
          certificate_attached INTEGER, inspected_at TEXT, note TEXT
        );
        CREATE TABLE IF NOT EXISTS press_equipment (
          press_id TEXT PRIMARY KEY, press_name TEXT, capacity_ton REAL, controller TEXT,
          operating_state TEXT, last_maintenance TEXT, next_planned_maintenance TEXT
        );
        CREATE TABLE IF NOT EXISTS dies (
          die_id TEXT PRIMARY KEY, item_code TEXT, rated_strokes INTEGER, accumulated_strokes INTEGER,
          last_repair TEXT, condition TEXT
        );
        CREATE TABLE IF NOT EXISTS press_readings (
          reading_id TEXT PRIMARY KEY, press_id TEXT, die_id TEXT, measured_at TEXT,
          pressure_mpa REAL, die_temperature_c REAL, stroke_spm REAL,
          vibration_mm_s REAL, current_a REAL, status TEXT
        );
        CREATE TABLE IF NOT EXISTS maintenance_predictions (
          prediction_id TEXT PRIMARY KEY, press_id TEXT, die_id TEXT, predicted_at TEXT,
          risk_score REAL, remaining_strokes INTEGER, risk_level TEXT,
          top_factors TEXT, recommendation TEXT, model_status TEXT
        );
        CREATE TABLE IF NOT EXISTS maintenance_history (
          maintenance_id TEXT PRIMARY KEY, press_id TEXT, die_id TEXT, occurred_at TEXT,
          category TEXT, symptom TEXT, action TEXT, downtime_min INTEGER, approver TEXT
        );
        CREATE TABLE IF NOT EXISTS process_trace (
          trace_id TEXT PRIMARY KEY, work_order TEXT, process TEXT, started_at TEXT,
          ended_at TEXT, equipment TEXT, quantity INTEGER, result TEXT, note TEXT
        );
        CREATE TABLE IF NOT EXISTS outgoing_inspections (
          inspection_id TEXT PRIMARY KEY, work_order TEXT, inspected_at TEXT,
          dimension_result TEXT, appearance_result TEXT, marking_result TEXT,
          sample_qty INTEGER, defect_qty INTEGER, final_result TEXT, approver TEXT
        );
        CREATE TABLE IF NOT EXISTS shipments (
          shipment_no TEXT PRIMARY KEY, work_order TEXT, planned_date TEXT, actual_date TEXT,
          quantity INTEGER, status TEXT, quality_approval TEXT
        );
        """
        with self._connect() as connection:
            connection.executescript(schema)
            if connection.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 0:
                self._seed(connection)
            self._initialize_knowledge(connection)

    @staticmethod
    def _seed(connection: sqlite3.Connection) -> None:
        connection.executemany("INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("WO-260901", "KP-101", "프레스 가공품 A", 12000, "MAT-260827-A", "PRS-01", "DIE-101", "2026-09-06", "마킹 완료", 88),
            ("WO-260902", "KP-205", "프레스 가공품 B", 8500, "MAT-260829-B", "PRS-02", "DIE-205", "2026-09-08", "전착 진행", 62),
            ("WO-260903", "KP-310", "프레스 가공품 C", 15000, "MAT-260901-C", "PRS-01", "DIE-310", "2026-09-10", "프레스 대기", 28),
        ])
        connection.executemany("INSERT INTO incoming_inspections VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
            ("II-260901", "MAT-260827-A", "A스틸", "SPCC 1.2T", 13000, 1.19, 58, "합격", 1, "2026-08-27 10:20", "성적서 확인"),
            ("II-260902", "MAT-260829-B", "B금속", "SPHC 2.0T", 9000, 1.96, 67, "조건부합격", 1, "2026-08-29 14:10", "두께 하한 재확인"),
            ("II-260903", "MAT-260901-C", "C소재", "SECC 0.8T", 16000, 0.81, 62, "보류", 0, "2026-09-01 09:40", "소재성적서 미첨부"),
        ])
        connection.executemany("INSERT INTO press_equipment VALUES (?,?,?,?,?,?,?)", [
            ("PRS-01", "프레스 1호기", 250, "PLC-A", "주의", "2026-08-10", "2026-09-05"),
            ("PRS-02", "프레스 2호기", 160, "PLC-B", "가동", "2026-08-20", "2026-09-20"),
        ])
        connection.executemany("INSERT INTO dies VALUES (?,?,?,?,?,?)", [
            ("DIE-101", "KP-101", 500000, 461200, "2026-07-28", "점검 필요"),
            ("DIE-205", "KP-205", 420000, 286500, "2026-08-15", "정상"),
            ("DIE-310", "KP-310", 350000, 338700, "2026-06-30", "교체 검토"),
        ])
        connection.executemany("INSERT INTO press_readings VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("RD-001", "PRS-01", "DIE-101", "2026-09-03 13:00", 18.4, 67.2, 42, 5.4, 38.8, "주의"),
            ("RD-002", "PRS-02", "DIE-205", "2026-09-03 13:00", 15.8, 54.6, 38, 2.7, 26.1, "정상"),
            ("RD-003", "PRS-01", "DIE-310", "2026-09-03 14:00", 19.1, 71.3, 41, 6.2, 41.5, "경고"),
        ])
        connection.executemany("INSERT INTO maintenance_predictions VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("MP-001", "PRS-01", "DIE-101", "2026-09-03 13:05", 0.72, 24500, "높음", "진동·누적스트로크·전류", "다음 작업 전 금형 정렬·가이드 점검", "시제품 데모·미검증"),
            ("MP-002", "PRS-02", "DIE-205", "2026-09-03 13:05", 0.21, 118000, "낮음", "누적스트로크", "계획정비 주기 유지", "시제품 데모·미검증"),
            ("MP-003", "PRS-01", "DIE-310", "2026-09-03 14:05", 0.89, 8200, "긴급", "진동·금형온도·전류·잔여수명", "가동 전 보전책임자 정밀점검", "시제품 데모·미검증"),
        ])
        connection.executemany("INSERT INTO maintenance_history VALUES (?,?,?,?,?,?,?,?,?)", [
            ("MH-26031", "PRS-01", "DIE-101", "2026-08-10", "예방정비", "가이드 마모", "가이드 교환·정렬", 75, "보전팀장"),
            ("MH-26027", "PRS-02", "DIE-205", "2026-07-29", "고장정비", "전류 상승·이상음", "모터 베어링 교체", 140, "생산팀장"),
        ])
        connection.executemany("INSERT INTO process_trace VALUES (?,?,?,?,?,?,?,?,?)", [
            ("TR-001", "WO-260901", "입고·수입검사", "2026-08-27 09:00", "2026-08-27 11:00", "검사대", 13000, "합격", "MAT-260827-A"),
            ("TR-002", "WO-260901", "프레스", "2026-08-29 08:00", "2026-08-30 18:00", "PRS-01/DIE-101", 11920, "완료", "80개 공정손실"),
            ("TR-003", "WO-260901", "전착", "2026-09-01 08:30", "2026-09-01 15:00", "전착라인", 11880, "완료", "40개 외관보류"),
            ("TR-004", "WO-260901", "마킹", "2026-09-02 09:00", "2026-09-02 16:40", "마킹기-01", 11860, "완료", "20개 마킹 NG"),
            ("TR-005", "WO-260902", "프레스", "2026-09-01 08:00", "2026-09-02 14:00", "PRS-02/DIE-205", 8460, "완료", "40개 공정손실"),
            ("TR-006", "WO-260902", "전착", "2026-09-03 08:00", None, "전착라인", 4100, "진행", "중간검사 정상"),
        ])
        connection.executemany("INSERT INTO outgoing_inspections VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("OI-260901", "WO-260901", "2026-09-03 10:20", "합격", "조건부합격", "합격", 80, 2, "조건부합격", "품질팀장"),
            ("OI-260902", "WO-260902", "2026-09-03 15:10", "합격", "합격", "합격", 50, 0, "공정중간검사", "김검사"),
        ])
        connection.executemany("INSERT INTO shipments VALUES (?,?,?,?,?,?,?)", [
            ("SH-260901", "WO-260901", "2026-09-05", None, 11858, "승인대기", "조건부 승인 검토"),
            ("SH-260902", "WO-260902", "2026-09-07", None, 8460, "공정진행", "미승인"),
        ])

    @staticmethod
    def _dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._dicts(connection.execute(sql, params).fetchall())

    def dashboard(self) -> dict[str, Any]:
        with self._connect() as connection:
            return {
                "active_work_orders": connection.execute("SELECT COUNT(*) FROM work_orders WHERE progress_pct < 100").fetchone()[0],
                "press_alerts": connection.execute("SELECT COUNT(*) FROM press_readings WHERE status != '정상'").fetchone()[0],
                "maintenance_risks": connection.execute("SELECT COUNT(*) FROM maintenance_predictions WHERE risk_level IN ('높음','긴급')").fetchone()[0],
                "incoming_holds": connection.execute("SELECT COUNT(*) FROM incoming_inspections WHERE result != '합격'").fetchone()[0],
                "shipment_pending": connection.execute("SELECT COUNT(*) FROM shipments WHERE status != '출하완료'").fetchone()[0],
            }

    def get_incoming_inspection(self, material_lot: str | None = None, issues_only: bool = False) -> list[dict[str, Any]]:
        sql, clauses, params = "SELECT * FROM incoming_inspections", [], []
        if material_lot:
            clauses.append("material_lot=?")
            params.append(material_lot)
        if issues_only:
            clauses.append("result!='합격'")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self._query(sql + " ORDER BY inspected_at DESC", tuple(params))

    def get_press_status(self, press_id: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT r.*,e.press_name,e.capacity_ton,e.operating_state,e.next_planned_maintenance
                 FROM press_readings r JOIN press_equipment e ON e.press_id=r.press_id"""
        return self._query(sql + (" WHERE r.press_id=?" if press_id else "") + " ORDER BY r.measured_at DESC", (press_id,) if press_id else ())

    def get_die_life(self, die_id: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT *, rated_strokes-accumulated_strokes AS nominal_remaining_strokes,
                        ROUND(CAST(accumulated_strokes*100.0/rated_strokes AS NUMERIC),1) AS usage_pct FROM dies"""
        return self._query(sql + (" WHERE die_id=?" if die_id else "") + " ORDER BY usage_pct DESC", (die_id,) if die_id else ())

    def get_maintenance_risks(self, press_id: str | None = None, urgent_only: bool = False) -> list[dict[str, Any]]:
        sql, clauses, params = "SELECT * FROM maintenance_predictions", [], []
        if press_id:
            clauses.append("press_id=?")
            params.append(press_id)
        if urgent_only:
            clauses.append("risk_level IN ('높음','긴급')")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self._query(sql + " ORDER BY risk_score DESC", tuple(params))

    def get_maintenance_history(self, press_id: str | None = None, die_id: str | None = None) -> list[dict[str, Any]]:
        sql, clauses, params = "SELECT * FROM maintenance_history", [], []
        if press_id:
            clauses.append("press_id=?")
            params.append(press_id)
        if die_id:
            clauses.append("die_id=?")
            params.append(die_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self._query(sql + " ORDER BY occurred_at DESC", tuple(params))

    def get_process_trace(self, work_order: str) -> dict[str, Any]:
        orders = self._query("SELECT * FROM work_orders WHERE work_order=?", (work_order,))
        if not orders:
            return {"work_order": None, "message": "작업지시를 찾지 못했습니다."}
        return {
            "work_order": orders[0],
            "incoming": self._query("SELECT * FROM incoming_inspections WHERE material_lot=?", (orders[0]["material_lot"],)),
            "processes": self._query("SELECT * FROM process_trace WHERE work_order=? ORDER BY started_at", (work_order,)),
            "outgoing": self._query("SELECT * FROM outgoing_inspections WHERE work_order=?", (work_order,)),
            "shipment": self._query("SELECT * FROM shipments WHERE work_order=?", (work_order,)),
        }

    def get_outgoing_inspection(self, work_order: str | None = None, issues_only: bool = False) -> list[dict[str, Any]]:
        sql, clauses, params = "SELECT * FROM outgoing_inspections", [], []
        if work_order:
            clauses.append("work_order=?")
            params.append(work_order)
        if issues_only:
            clauses.append("final_result!='합격'")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self._query(sql + " ORDER BY inspected_at DESC", tuple(params))

    def get_shipment_status(self, work_order: str | None = None) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM shipments" + (" WHERE work_order=?" if work_order else "") + " ORDER BY planned_date", (work_order,) if work_order else ())

    def get_work_orders(self) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM work_orders ORDER BY due_date")

    def get_process_rows(self) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM process_trace ORDER BY started_at DESC")

    @staticmethod
    def _initialize_knowledge(connection: sqlite3.Connection) -> None:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                document_id TEXT PRIMARY KEY, filename TEXT, content TEXT,
                source TEXT, status TEXT
            );
            CREATE TABLE IF NOT EXISTS rules (
                rule_id TEXT PRIMARY KEY, name TEXT, source_table TEXT,
                condition TEXT, owner TEXT, action TEXT, source_document TEXT,
                revision TEXT, status TEXT
            );
            CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);
        """)
        directory = Path(__file__).resolve().parent.parent / "sample_docs" / "knowledge"
        for path in sorted(directory.glob("*.md")):
            connection.execute(
                "INSERT OR IGNORE INTO knowledge_documents (document_id, filename, content, source, status) VALUES (?, ?, ?, ?, ?)",
                (path.stem.split("_")[0], path.name, path.read_text(), "로컬 샘플", "미승인 샘플"),
            )
        rules_path = directory / "rules.json"
        if rules_path.exists():
            for rule in json.loads(rules_path.read_text()):
                connection.execute("INSERT OR IGNORE INTO rules VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    tuple(rule[key] for key in (
                        "rule_id", "name", "source_table", "condition", "owner", "action",
                        "source_document", "revision", "status")))

    def knowledge_documents(self) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM knowledge_documents ORDER BY document_id")

    def search_knowledge(self, query: str) -> list[dict[str, Any]]:
        # Local lexical retrieval: Korean bigrams tolerate particles and spacing.
        words = re.findall(r"[가-힣a-zA-Z0-9]+", query.lower())
        terms = set(words + [word[i:i+2] for word in words for i in range(len(word)-1)])
        terms = {term for term in terms if len(term) >= 2}
        matches = []
        for doc in self.knowledge_documents():
            content = doc["content"] or ""
            searchable = (doc["filename"] + " " + content).lower()
            score = sum(term in searchable for term in terms)
            if score and content:
                matches.append({"filename": doc["filename"], "document_id": doc["document_id"],
                                "text": content, "match_count": score, "source": doc["source"]})
        return sorted(matches, key=lambda item: (-item["match_count"], item["filename"]))[:5]

    def get_rules(self) -> list[dict[str, Any]]:
        return self.table_records("rules")

    def setting(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM app_settings WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    def save_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO app_settings VALUES (?, ?)", (key, value))

    def save_uploaded_document(self, file_id: str, filename: str, content: str | None) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO knowledge_documents VALUES (?, ?, ?, ?, ?)",
                (file_id, filename, content, "업로드 문서", "File Search 인덱싱 완료"))

    @staticmethod
    def _dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._dicts(connection.execute(sql, params).fetchall())

    def table_inventory(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            existing = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            return [
                {"table": name, "label": label, "exists": name in existing,
                 "count": connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                 if name in existing else 0}
                for name, label in self.TABLE_LABELS.items()
            ]

    def table_records(self, table: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if table not in self.TABLE_LABELS:
            raise ValueError("조회할 수 없는 테이블입니다.")
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("조회 범위가 올바르지 않습니다.")
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                return []
            # Stable paging uses the table's declared columns; identifiers come from SQLite.
            columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            order = ", ".join('"' + row[1].replace('"', '""') + '"' for row in columns)
            return self._dicts(connection.execute(
                f'SELECT * FROM "{table}" ORDER BY {order} LIMIT ? OFFSET ?', (limit, offset)
            ).fetchall())

    TABLE_LABELS = {'work_orders': '작업지시', 'incoming_inspections': '수입검사', 'press_equipment': '프레스 설비', 'dies': '금형', 'press_readings': '설비 측정', 'maintenance_predictions': '예지보전 예측', 'maintenance_history': '정비 이력', 'process_trace': '공정 추적', 'outgoing_inspections': '출하검사', 'shipments': '출하', 'rules': '검토 규칙'}

class _PostgresRow(dict):
    """Dictionary row with SQLite-compatible integer indexing for shared code."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class _PostgresCursor:
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def _row(self, row: Any) -> _PostgresRow | None:
        if row is None:
            return None
        names = [column.name for column in self.cursor.description or ()]
        return _PostgresRow(zip(names, row))

    def fetchone(self) -> _PostgresRow | None:
        return self._row(self.cursor.fetchone())

    def fetchall(self) -> list[_PostgresRow]:
        return [self._row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _PostgresConnection:
    """Small adapter so repository query methods stay backend-independent."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s").replace("INSERT OR IGNORE INTO", "INSERT INTO")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _PostgresCursor:
        if "INSERT OR IGNORE INTO" in sql:
            sql = self._sql(sql) + " ON CONFLICT DO NOTHING"
        cursor = self.connection.execute(self._sql(sql), params)
        return _PostgresCursor(cursor)

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        with self.connection.cursor() as cursor:
            cursor.executemany(self._sql(sql), params)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def __enter__(self) -> "_PostgresConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.connection.close()


class PostgresRepository(KwangsungRepository):
    """PostgreSQL + pgvector Data Hub used when DATABASE_URL is configured."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.db_path = None
        self._initialize()

    def _connect(self, *, register_vector_type: bool = True) -> _PostgresConnection:
        try:
            import psycopg
            from pgvector.psycopg import register_vector
        except ImportError as exc:
            raise RuntimeError("PostgreSQL 사용에는 psycopg[binary] 설치가 필요합니다.") from exc
        raw = psycopg.connect(self.database_url)
        try:
            if register_vector_type:
                register_vector(raw)
        except Exception:
            raw.close()
            raise
        return _PostgresConnection(raw)

    def _initialize(self) -> None:
        # A fresh database has no vector type until this transaction commits.
        with self._connect(register_vector_type=False) as connection:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        super()._initialize()
        with self._connect() as connection:
            connection.execute("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS embedding vector(1536)")
            connection.execute("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS embedding_model TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS knowledge_documents_embedding_idx ON knowledge_documents USING hnsw (embedding vector_cosine_ops)")

    def table_inventory(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                {"table": name, "label": label,
                 "exists": bool(connection.execute(
                     "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?", (name,)
                 ).fetchone()),
                 "count": connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                 if connection.execute(
                     "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?", (name,)
                 ).fetchone() else 0}
                for name, label in self.TABLE_LABELS.items()
            ]

    def table_records(self, table: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if table not in self.TABLE_LABELS:
            raise ValueError("조회할 수 없는 테이블입니다.")
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("조회 범위가 올바르지 않습니다.")
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?", (table,)
            ).fetchone()
            if not exists:
                return []
            columns = connection.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=? ORDER BY ordinal_position",
                (table,),
            ).fetchall()
            order = ", ".join('"' + row[0].replace('"', '""') + '"' for row in columns)
            return [dict(row) for row in connection.execute(
                f'SELECT * FROM "{table}" ORDER BY {order} LIMIT ? OFFSET ?', (limit, offset)
            ).fetchall()]

    def save_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (key, value))

    def save_uploaded_document(self, file_id: str, filename: str, content: str | None, embedding: list[float] | None = None, embedding_model: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute("""INSERT INTO knowledge_documents (document_id, filename, content, source, status, embedding, embedding_model)
                VALUES (?, ?, ?, '업로드 문서', '인덱싱 완료', ?, ?)
                ON CONFLICT (document_id) DO UPDATE SET filename=EXCLUDED.filename, content=EXCLUDED.content,
                status=EXCLUDED.status, embedding=EXCLUDED.embedding, embedding_model=EXCLUDED.embedding_model""",
                (file_id, filename, content, embedding, embedding_model))

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> int:
        if table not in self.TABLE_LABELS or table == "knowledge_documents":
            raise ValueError("마이그레이션할 수 없는 테이블입니다.")
        if not rows:
            return 0
        columns = list(rows[0])
        names = ", ".join(f'"{column}"' for column in columns)
        placeholders = ", ".join("%s" for _ in columns)
        sql = f'INSERT INTO "{table}" ({names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
        with self._connect() as connection:
            connection.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
        return len(rows)

    def insert_knowledge_rows(self, rows: list[dict[str, Any]]) -> int:
        """Insert migrated documents while preserving IDs and optional vectors."""
        if not rows:
            return 0
        sql = """INSERT INTO knowledge_documents
            (document_id, filename, content, source, status, embedding, embedding_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET filename=EXCLUDED.filename,
              content=EXCLUDED.content, source=EXCLUDED.source, status=EXCLUDED.status,
              embedding=COALESCE(EXCLUDED.embedding, knowledge_documents.embedding),
              embedding_model=COALESCE(EXCLUDED.embedding_model, knowledge_documents.embedding_model)"""
        with self._connect() as connection:
            connection.executemany(sql, [(
                row.get("document_id"), row.get("filename"), row.get("content"),
                row.get("source"), row.get("status"), row.get("embedding"), row.get("embedding_model"),
            ) for row in rows])
        return len(rows)

    def reset_data_for_migration(self) -> None:
        """Clear demo/previous rows before a full SQLite replacement import."""
        tables = [*self.TABLE_LABELS.keys(), "knowledge_documents", "app_settings"]
        with self._connect() as connection:
            connection.execute("TRUNCATE TABLE " + ", ".join(f'\"{table}\"' for table in tables) + " CASCADE")

    def vector_search_knowledge(self, embedding: list[float], limit: int = 5) -> list[dict[str, Any]]:
        """Nearest-neighbor retrieval for callers that provide a 1536-d embedding."""
        if not 1 <= limit <= 50:
            raise ValueError("조회 범위가 올바르지 않습니다.")
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("""
                SELECT document_id, filename, content, source, status,
                       embedding <=> ?::vector AS distance
                FROM knowledge_documents
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> ?::vector
                LIMIT ?
            """, (embedding, embedding, limit)).fetchall()]


def create_repository(sqlite_path: str | Path) -> KwangsungRepository:
    """Use PostgreSQL in configured environments and retain SQLite for offline tests."""
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    return PostgresRepository(database_url) if database_url else KwangsungRepository(sqlite_path)
