import math
import random
from typing import List, Dict, Any, Optional

JsonDict = Dict[str, Any]


class DifferentialPrivacy:
    def __init__(self, epsilon: float = 1.0, delta: float = 1e-5):
        self.epsilon = epsilon
        self.delta = delta

    def _laplace(self, scale: float) -> float:
        u = random.uniform(-0.5, 0.5)
        return -scale * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))

    def add_laplace_noise(self, value: float, sensitivity: float = 1.0) -> float:
        scale = sensitivity / self.epsilon
        return float(value + self._laplace(scale))

    def dp_count(self, n: int) -> float:
        return self.add_laplace_noise(n, sensitivity=1.0)

    def dp_mean(self, values: List[float], sensitivity: float = 1.0) -> float:
        if not values:
            return 0.0
        true_mean = sum(values) / len(values)
        # Sensitivity for mean depends on range; assume normalized or pre-bounded range [0,1] unless specified.
        return self.add_laplace_noise(true_mean, sensitivity=sensitivity)


def dp_aggregate_summary(values: List[float], epsilon: float = 0.8) -> JsonDict:
    dp = DifferentialPrivacy(epsilon=epsilon)
    if not values:
        return {"count": 0, "mean": 0.0}
    return {
        "count": dp.dp_count(len(values)),
        "mean": dp.dp_mean(values, sensitivity=1.0),
    }