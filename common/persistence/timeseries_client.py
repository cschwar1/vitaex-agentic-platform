import os
from typing import Any, Dict, List, Optional
import psycopg2
from psycopg2.extras import execute_values
from loguru import logger

JsonDict = Dict[str, Any]


class TimeseriesClient:
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("TIMESERIES_DSN", "postgresql://postgres:password@localhost:5432/vitaex")
        self._conn = psycopg2.connect(self.dsn)
        self._conn.autocommit = True
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS measurements (
                    user_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    value DOUBLE PRECISION,
                    meta JSONB DEFAULT '{}'::jsonb
                );
            """)
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
            cur.execute("""
                SELECT create_hypertable('measurements', 'ts', if_not_exists => TRUE);
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_measurements_user_metric ON measurements(user_id, metric, ts DESC)")

    def insert_measurements(self, rows: List[JsonDict]) -> int:
        if not rows:
            return 0
        with self._conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO measurements (user_id, metric, ts, value, meta)
                VALUES %s
                ON CONFLICT DO NOTHING
            """, [
                (r["user_id"], r["metric"], r["ts"], r.get("value"), r.get("meta", {})) for r in rows
            ])
        logger.info(f"Inserted {len(rows)} measurements")
        return len(rows)

    def query(self, user_id: str, metric: str, start: Optional[str] = None, end: Optional[str] = None, limit: int = 1000) -> List[JsonDict]:
        with self._conn.cursor() as cur:
            params = [user_id, metric]
            where = "WHERE user_id=%s AND metric=%s"
            if start:
                where += " AND ts >= %s"
                params.append(start)
            if end:
                where += " AND ts <= %s"
                params.append(end)
            cur.execute(f"""
                SELECT ts, value, meta
                FROM measurements
                {where}
                ORDER BY ts DESC
                LIMIT %s
            """, params + [limit])
            rows = cur.fetchall()
            return [{"ts": r[0].isoformat(), "value": r[1], "meta": r[2]} for r in rows]