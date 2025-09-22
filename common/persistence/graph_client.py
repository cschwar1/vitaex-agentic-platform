import os
from typing import Dict, Any, List, Tuple, Optional
from neo4j import GraphDatabase
from loguru import logger

JsonDict = Dict[str, Any]


class GraphClient:
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self._driver.close()

    def sync_graph(self, graph_data: JsonDict) -> None:
        nodes: List[JsonDict] = graph_data.get("nodes", [])
        edges: List[JsonDict] = graph_data.get("edges", [])
        logger.info(f"Syncing graph to Neo4j nodes={len(nodes)} edges={len(edges)}")

        with self._driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE")
            # Upsert nodes
            for n in nodes:
                session.run(
                    """
                    MERGE (node:Node {id: $id})
                    SET node += $props
                    """,
                    id=n["id"],
                    props={
                        "label": n.get("label"),
                        "title": n.get("title"),
                        "group": n.get("group"),
                    },
                )
            # Upsert relationships
            for e in edges:
                session.run(
                    """
                    MATCH (a:Node {id: $from})
                    MATCH (b:Node {id: $to})
                    MERGE (a)-[r:REL {type: $type}]->(b)
                    SET r += $props
                    """,
                    **{
                        "from": e["from"],
                        "to": e["to"],
                        "type": e.get("label", "REL"),
                        "props": {
                            "arrows": e.get("arrows"),
                            "width": e.get("width"),
                            "confidence": e.get("confidence"),
                            "title": e.get("title"),
                        },
                    },
                )

    def query_neighbors(self, node_id: str, max_hops: int = 2) -> List[JsonDict]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n:Node {id: $node_id})-[r*1..$max_hops]-(m)
                RETURN DISTINCT m.id AS node_id
                """,
                node_id=node_id,
                max_hops=max_hops,
            )
            return [{"node_id": rec["node_id"]} for rec in result]

    def find_by_label(self, label: str) -> List[JsonDict]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n:Node {label: $label})
                RETURN n.id AS id, n.title AS title, n.group AS group
                """,
                label=label,
            )
            return [{"id": r["id"], "title": r["title"], "group": r["group"]} for r in result]