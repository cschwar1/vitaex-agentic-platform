from typing import List, Dict, Any, Callable
from loguru import logger

JsonDict = Dict[str, Any]


class FLClient:
    def __init__(self, client_id: str):
        self.client_id = client_id

    def get_update(self) -> JsonDict:
        # Return model gradients or weights delta
        return {"weights": [], "metadata": {"client_id": self.client_id}}

    def apply_global(self, weights: List[float]) -> None:
        # Apply new model weights
        pass


class FLAggregator:
    def __init__(self, dp_hook: Callable[[List[float]], List[float]] | None = None):
        self.dp_hook = dp_hook

    def aggregate(self, client_updates: List[JsonDict]) -> List[float]:
        # Simple FedAvg on weights
        if not client_updates:
            return []
        # Expect all clients to have same weight length; production code needs robust validation.
        weights_list = [u["weights"] for u in client_updates if "weights" in u]
        if not weights_list or not weights_list[0]:
            return []
        n = len(weights_list[0])
        avg = [0.0] * n
        for w in weights_list:
            for i in range(n):
                avg[i] += w[i]
        avg = [v / len(weights_list) for v in avg]
        if self.dp_hook:
            avg = self.dp_hook(avg)
        logger.info(f"Aggregated {len(client_updates)} client updates")
        return avg