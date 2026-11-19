"""
StorageHub — Rate limiting via FastAPI Depends (sans slowapi decorator bugs)
Deux backends :
  - mémoire (défaut) : suffisant pour une seule instance
  - Redis (REDIS_URL) : fenêtre glissante partagée entre instances/workers
"""
import logging
import time
from collections import defaultdict
from fastapi import Depends, HTTPException, Request

from app.auth import AuthContext, get_auth_context
from app.config import get_plan, settings

logger = logging.getLogger("storagehub.ratelimit")


class _InMemoryRateLimiter:
    """Fenêtre glissante par clé — compteurs locaux au processus."""

    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def check(self, key: str, max_calls: int, period: int):
        now = time.time()
        bucket = self._buckets[key]
        self._buckets[key] = [t for t in bucket if now - t < period]
        if len(self._buckets[key]) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded — max {max_calls} requests per {period}s",
            )
        self._buckets[key].append(now)


class _RedisRateLimiter:
    """
    Fenêtre glissante distribuée via Redis sorted set.
    Le script Lua rend le check-and-add atomique entre instances.
    """

    _LUA = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
    local count = redis.call('ZCARD', key)
    if count >= limit then
        return 0
    end
    redis.call('ZADD', key, now, now .. ':' .. count .. ':' .. math.random(1000000))
    redis.call('PEXPIRE', key, window)
    return 1
    """

    def __init__(self, url: str):
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(url, decode_responses=True)
        self._script = self._redis.register_script(self._LUA)

    async def check(self, key: str, max_calls: int, period: int):
        try:
            ok = await self._script(
                keys=[f"rl:{key}"],
                args=[int(time.time() * 1000), period * 1000, max_calls],
            )
        except Exception as exc:
            # Redis indisponible : ne pas bloquer le service (fail-open)
            logger.warning(f"Redis rate limiter error, allowing request: {exc}")
            return
        if not ok:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded — max {max_calls} requests per {period}s",
            )


def _make_store():
    """Redis si REDIS_URL est défini et le package installé, sinon mémoire."""
    if settings.redis_url:
        try:
            store = _RedisRateLimiter(settings.redis_url)
            logger.info("Rate limiter: Redis backend enabled")
            return store
        except ImportError:
            logger.warning("REDIS_URL set but 'redis' package missing — falling back to in-memory")
        except Exception as exc:
            logger.warning(f"Redis rate limiter init failed ({exc}) — falling back to in-memory")
    return _InMemoryRateLimiter()


_store = _make_store()


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
        await _store.check(f"{self.name}:{identity}", self.max_calls, self.period)


# Limites prédéfinies
upload_limit  = RateLimit("upload",  max_calls=60,  period=60)   # 60 uploads/minute
bulk_limit    = RateLimit("bulk",    max_calls=10,  period=60)   # 10 bulk/minute
url_limit     = RateLimit("url",     max_calls=20,  period=60)   # 20 from-url/minute
global_limit  = RateLimit("global",  max_calls=300, period=60)   # 300 req/minute global


async def plan_upload_limit(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """
    Rate limit d'upload appliquant le quota `upload_rate_per_min` du plan
    du client. FastAPI met en cache get_auth_context : l'auth n'est
    résolue qu'une fois par requête. La clé maître interne n'est pas limitée.
    """
    if auth.is_master:
        return
    plan = get_plan(auth.plan)
    identity = auth.client_id or _get_ip(request)
    await _store.check(f"upload:{identity}", plan["upload_rate_per_min"], 60)

# Pour compatibilité avec main.py (slowapi n'est plus nécessaire mais gardé pour l'exception handler)
class _FakeLimiter:
    """Shim pour éviter d'importer slowapi partout."""
    def limit(self, *a, **kw):
        def decorator(f):
            return f
        return decorator

limiter = _FakeLimiter()
