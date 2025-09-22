from typing import Any, Dict, Optional
from datetime import datetime, timezone
from loguru import logger

JsonDict = Dict[str, Any]


def audit_event(action: str, user_id: Optional[str] = None, actor: str = "system", details: Optional[JsonDict] = None,
                correlation_id: Optional[str] = None) -> None:
    evt = {
        "action": action,
        "user_id": user_id,
        "actor": actor,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id
    }
    logger.bind(audit=True).info(f"AUDIT {evt}")