"""Migrate the local demo SQLite data hub into PostgreSQL + pgvector."""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kwangsung_agent.data_hub import PostgresRepository

BUSINESS_TABLES = tuple(PostgresRepository.TABLE_LABELS)


def rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"').fetchall()]


def migrate(source: Path, database_url: str, replace: bool = True) -> dict[str, int]:
    if not source.exists():
        raise FileNotFoundError(f"SQLite 원본을 찾을 수 없습니다: {source}")
    # Read and validate all source tables before opening a replacement transaction.
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as sqlite:
        payload = {table: rows(sqlite, table) for table in (*BUSINESS_TABLES, "knowledge_documents", "app_settings")}
    target = PostgresRepository(database_url)
    counts = {table: len(data) for table, data in payload.items()}
    with target._connect() as connection:
        if replace:
            names = ", ".join(f'"{table}"' for table in payload)
            connection.execute("TRUNCATE TABLE " + names)
        for table, data in payload.items():
            columns = [row[0] for row in connection.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=? ORDER BY ordinal_position", (table,)
            ).fetchall()]
            for row in data:
                if not set(row) <= set(columns):
                    raise ValueError(f"원본 열이 대상 스키마와 다릅니다: {table}")
                selected = [column for column in columns if column in row]
                names = ", ".join(f'"{column}"' for column in selected)
                placeholders = ", ".join("?" for _ in selected)
                connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                                   tuple(row[column] for column in selected))

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/kwangsung_demo.db"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL"))
    parser.add_argument("--append", action="store_true", help="기존 PostgreSQL 행을 보존하고 누락 행만 추가")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url 또는 DATABASE_URL이 필요합니다.")
    counts = migrate(args.source, args.database_url, replace=not args.append)
    print("PostgreSQL 마이그레이션 완료")
    for table, count in counts.items():
        print(f"- {table}: {count}건 처리")


if __name__ == "__main__":
    main()
