from typing import Dict, Any, Optional
from datetime import datetime, timezone

JsonDict = Dict[str, Any]


class ConsentStore:
    def __init__(self):
        self._store: Dict[str, Dict[str, JsonDict]] = {}

    def grant(self, user_id: str, purpose: str, scope: str, expires_at: Optional[str] = None) -> None:
        self._store.setdefault(user_id, {})
        self._store[user_id][purpose] = {
            "scope": scope,
            "granted_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at,
        }

    def revoke(self, user_id: str, purpose: str) -> None:
        if user_id in self._store and purpose in self._store[user_id]:
            del self._store[user_id][purpose]

    def check(self, user_id: str, purpose: str) -> bool:
        purposes = self._store.get(user_id, {})
        record = purposes.get(purpose)
        if not record:
            return False
        expires_at = record.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc):
            return False
        return True


consent_store = ConsentStore()