"""
StorageHub v2 — Storage Service
FastAPI application entry point
"""
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.config import settings
from app.database import init_db
from app.routers import accounts, files, health, public
from app.routers import webhooks
from app.schemas import ApiError, ErrorCode

_start_time = time.time()


# ── Exception handlers ─────────────────────────────────────────────────────────
def _error_code(exc: HTTPException) -> str:
    d = str(exc.detail or "")
    if "Missing" in d and "API" in d:                               return "MISSING_API_KEY"
    if "Invalid API key" in d:                                      return "INVALID_API_KEY"
    if "HMAC" in d:                                                 return "INVALID_HMAC"
    if "Access denied" in d:                                        return "ACCESS_DENIED"
    if "not found" in d.lower():                                    return "FILE_NOT_FOUND"
    if "too large" in d.lower():                                    return "FILE_TOO_LARGE"
    if "quota exceeded" in d.lower():                               return "QUOTA_EXCEEDED"
    if "empty" in d.lower():                                        return "EMPTY_FILE"
    if "executable" in d.lower() or "script" in d.lower():         return "DANGEROUS_FILE"
    if "malware" in d.lower() or "virus" in d.lower() or "eicar" in d.lower(): return "MALWARE_DETECTED"
    if "rejected" in d.lower() and ("eicar" in d.lower() or "dangerous" in d.lower()): return "MALWARE_DETECTED"
    if "rejected" in d.lower():                                     return "DANGEROUS_FILE"
    if "invalid category" in d.lower():                             return "INVALID_CATEGORY"
    if "not allowed" in d.lower() and "category" in d.lower():     return "INVALID_CATEGORY"
    if "not allowed" in d.lower():                                  return "INVALID_MIME"
    if "signed" in d.lower():                                       return "SIGNED_URL_INVALID"
    return {
        401: "MISSING_API_KEY", 403: "FORBIDDEN",
        404: "FILE_NOT_FOUND",  413: "FILE_TOO_LARGE",
        429: "RATE_LIMIT_EXCEEDED",
    }.get(exc.status_code, "INTERNAL_ERROR")


async def _http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiError(request_id=rid, error=str(exc.detail or ""),
                         code=_error_code(exc)).model_dump(),
    )


async def _validation_exc_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = exc.errors()
    field = errors[0].get("loc", [""])[-1] if errors else None
    return JSONResponse(
        status_code=422,
        content=ApiError(
            request_id=rid,
            error="Validation error — check request parameters",
            code=ErrorCode.INVALID_CATEGORY,
            detail=str(errors[0].get("msg", "")) if errors else None,
            field=str(field) if field else None,
        ).model_dump(),
    )


async def _global_exc_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=500,
        content=ApiError(
            request_id=rid,
            error="Internal server error",
            code=ErrorCode.INTERNAL_ERROR,
            detail=str(exc) if not settings.is_production else None,
        ).model_dump(),
    )


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    # Créer les dossiers de stockage
    for cat in ["avatars", "kyc", "receipts", "thumbnails"]:
        (settings.upload_path / cat).mkdir(parents=True, exist_ok=True)

    # Initialiser la base de données
    await init_db()

    # Démarrer le planificateur de tâches (purge quotidienne)
    from app.tasks.purge import start_scheduler
    _scheduler = start_scheduler()

    print(f"[STORAGEHUB] v2.0 started — env={settings.app_env} | backend={settings.storage_backend}")
    print(f"[STORAGEHUB] Upload root: {settings.upload_path.resolve()}")
    yield

    if _scheduler:
        _scheduler.shutdown(wait=False)
    print("[STORAGEHUB] Shutting down")


# ── Application FastAPI ────────────────────────────────────────────────────────
app = FastAPI(
    exception_handlers={
        HTTPException:          _http_exc_handler,
        RequestValidationError: _validation_exc_handler,
        Exception:              _global_exc_handler,
    },
    title="StorageHub — Secure Storage API v2",
    description=(
        "## API de stockage de fichiers sécurisée — multi-tenant SaaS\n\n"
        "### Nouveautés v2\n"
        "- **Rate limiting** : 60 uploads/min, 300 req/min global\n"
        "- **Chiffrement au repos** : KYC et reçus chiffrés AES-256\n"
        "- **Scan antivirus** : EICAR + magic bytes + patterns PDF\n"
        "- **Miniatures** : générées automatiquement pour les images\n"
        "- **Webhooks** : notifications HTTP sur événements fichiers\n"
        "- **Upload bulk** : plusieurs fichiers en une requête\n"
        "- **Import URL** : importer depuis une URL distante\n"
        "- **Versioning** : historique des versions d'un fichier\n"
        "- **Tags** : métadonnées custom sur chaque fichier\n"
        "- **Pagination** : liste paginée et triable\n"
        "- **Backend S3** : Cloudflare R2 / MinIO configurable\n\n"
        "### Authentification\n"
        "Tous les endpoints `/v1/` requièrent **`X-API-Key`**.\n\n"
        "En production, ajouter **`X-Timestamp`** et **`X-Signature`** (HMAC-SHA256).\n"
    ),
    version="2.0.0",
    contact={"name": "WIB Company — Engineering", "email": "tech@wibcompany.com"},
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    openapi_tags=[
        {"name": "files",    "description": "Upload, download, bulk, from-url, versioning, tags, thumbnails"},
        {"name": "public",   "description": "Accès public aux avatars"},
        {"name": "webhooks", "description": "Gestion des webhooks de notification"},
        {"name": "accounts", "description": "Comptes SaaS, clés API, stats"},
        {"name": "monitoring","description": "Santé, métriques, liveness probe"},
    ],
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
if settings.is_production:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Service-Version", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Service-Version", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(files.router)
app.include_router(accounts.router)
app.include_router(webhooks.router)
app.include_router(health.router)
app.include_router(public.router)

# ── UI statique ────────────────────────────────────────────────────────────────
ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
if os.path.exists(ui_path):
    app.mount("/ui", StaticFiles(directory=ui_path, html=True), name="ui")


# ── Middleware : Request ID + timing ──────────────────────────────────────────
@app.middleware("http")
async def add_integration_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"]      = request_id
    response.headers["X-Service-Version"] = "2.0.0"
    response.headers["X-Response-Time"]   = f"{elapsed_ms}ms"

    if not settings.is_production and request.url.path.startswith("/ui"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


# ── Endpoints racine ──────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    index = os.path.join(ui_path, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"service": "StorageHub", "version": "2.0.0",
            "uptime_seconds": round(time.time() - _start_time, 1)}


@app.get("/test", include_in_schema=False)
async def test_ui():
    test_page = os.path.join(ui_path, "test.html")
    if os.path.exists(test_page):
        return FileResponse(test_page)
    return JSONResponse(status_code=404, content={"error": "test.html not found"})


@app.get("/v1/ping", tags=["monitoring"], summary="Liveness probe")
async def ping():
    return {"pong": True, "version": "2.0.0", "service": "storagehub"}
