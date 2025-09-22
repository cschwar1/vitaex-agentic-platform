from typing import List, Dict, Any, Optional
from loguru import logger

from common.persistence.vector_client import VectorClient
from common.persistence.graph_client import GraphClient

JsonDict = Dict[str, Any]


class HybridRetriever:
    def __init__(self, vector_client: VectorClient, graph_client: GraphClient):
        self.vec = vector_client
        self.graph = graph_client

    def retrieve(self, namespace: str, embedding: List[float], graph_node_id: Optional[str] = None, k: int = 5) -> List[JsonDict]:
        vector_hits = self.vec.search(namespace, embedding, k=k)
        graph_hits: List[JsonDict] = []
        if graph_node_id:
            neighbors = self.graph.query_neighbors(graph_node_id, max_hops=2)
            graph_hits = [{"id": n["node_id"], "content": f"Graph node {n['node_id']}", "score": 0.5, "metadata": {"source": "graph"}} for n in neighbors[:k]]
        # Combine and de-duplicate
        combined = vector_hits + graph_hits
        seen = set()
        unique = []
        for hit in combined:
            hid = hit.get("id") or hit.get("metadata", {}).get("id")
            if hid and hid not in seen:
                seen.add(hid)
                unique.append(hit)
        logger.debug(f"HybridRetriever returned {len(unique)} results")
        return unique