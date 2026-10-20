"""
StorageHub — Rate limiting via FastAPI Depends (sans slowapi decorator bugs)
Implémentation en mémoire — suffisant pour une instance ; Redis pour multi-instance.
"""
import time
from collections import defaultdict
from fastapi import Depends, HTTPException, Request


class _InMemoryRateLimiter:
    """Fenêtre glissante par IP."""

    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_calls: int, period: int):
        now = time.time()
        bucket = self._buckets[key]
        # Supprimer les timestamps expirés
        self._buckets[key] = [t for t in bucket if now - t < period]
        if len(self._buckets[key]) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded — max {max_calls} requests per {period}s",
            )
        self._buckets[key].append(now)


_store = _InMemoryRateLimiter()


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Dépendances prêtes à l'emploi ──────────────────────────────────────────────
class RateLimit:
    """
    Usage : Depends(RateLimit("upload", max_calls=60, period=60))
    Chaque limiteur nommé possède son propre compteur. L'identité est la clé API
    (isolation multi-tenant) avec repli sur l'IP si absente.
    """
    def __init__(self, name: str = "default", max_calls: int = 300, period: int = 60):
        self.name = name
        self.max_calls = max_calls
        self.period = period

    async def __call__(self, request: Request):
        identity = request.headers.get("x-api-key") or _get_ip(request)
        _store.check(f"{self.name}:{identity}", self.max_calls, self.period)


# Limites prédéfinies
upload_limit  = RateLimit("upload",  max_calls=60,  period=60)   # 60 uploads/minute
bulk_limit    = RateLimit("bulk",    max_calls=10,  period=60)   # 10 bulk/minute
url_limit     = RateLimit("url",     max_calls=20,  period=60)   # 20 from-url/minute
global_limit  = RateLimit("global",  max_calls=300, period=60)   # 300 req/minute global

# Pour compatibilité avec main.py (slowapi n'est plus nécessaire mais gardé pour l'exception handler)
class _FakeLimiter:
    """Shim pour éviter d'importer slowapi partout."""
    def limit(self, *a, **kw):
        def decorator(f):
            return f
        return decorator

limiter = _FakeLimiter()
