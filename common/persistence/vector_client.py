import os
from typing import Any, Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import execute_values, Json
from loguru import logger

JsonDict = Dict[str, Any]


class VectorClient:
    def __init__(self, dsn: Optional[str] = None, dim: int = 1536):
        self.dsn = dsn or os.getenv("VECTOR_DSN", "postgresql://postgres:password@localhost:5432/vitaex")
        self.dim = dim
        self._conn = psycopg2.connect(self.dsn)
        self._conn.autocommit = True
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    embedding VECTOR(%s) NOT NULL
                )
            """, (self.dim,))
            cur.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_namespace ON embeddings(namespace)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_metadata ON embeddings USING GIN(metadata)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_embedding ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")

    def upsert(self, items: List[Tuple[str, str, str, JsonDict, List[float]]]) -> int:
        if not items:
            return 0
        with self._conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO embeddings (id, namespace, content, metadata, embedding)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                  content = EXCLUDED.content,
                  metadata = EXCLUDED.metadata,
                  embedding = EXCLUDED.embedding
            """, items, template="(%s,%s,%s,%s,%s)")
        logger.info(f"Upserted {len(items)} embeddings")
        return len(items)

    def search(self, namespace: str, query_embedding: List[float], k: int = 5, metadata_filter: Optional[JsonDict] = None) -> List[JsonDict]:
        where = "namespace = %s"
        params: List[Any] = [namespace]
        if metadata_filter:
            where += " AND metadata @> %s"
            params.append(Json(metadata_filter))
        sql = f"""
            SELECT id, content, metadata, 1 - (embedding <=> %s::vector) AS score
            FROM embeddings
            WHERE {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, [query_embedding] + params + [query_embedding, k])
            rows = cur.fetchall()
            return [{"id": r[0], "content": r[1], "metadata": r[2], "score": float(r[3])} for r in rows]