"""
StorageHub — Storage Service
FastAPI application entry point — prêt pour l'intégration
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
from app.schemas import ApiError, ErrorCode

_start_time = time.time()


# ── Exception handlers (définis avant FastAPI() pour être passés au constructeur)
def _error_code(exc: HTTPException) -> str:
    d = str(exc.detail or "")
    if "Missing" in d and "API" in d:                                    return "MISSING_API_KEY"
    if "Invalid API key" in d:                                           return "INVALID_API_KEY"
    if "HMAC" in d:                                                      return "INVALID_HMAC"
    if "Access denied" in d:                                             return "ACCESS_DENIED"
    if "not found" in d.lower():                                         return "FILE_NOT_FOUND"
    if "too large" in d.lower():                                         return "FILE_TOO_LARGE"
    if "empty" in d.lower():                                             return "EMPTY_FILE"
    if "executable" in d.lower() or "script" in d.lower():              return "DANGEROUS_FILE"
    if "invalid category" in d.lower():                                  return "INVALID_CATEGORY"
    if "not allowed" in d.lower() and "category" in d.lower():          return "INVALID_CATEGORY"
    if "not allowed" in d.lower():                                       return "INVALID_MIME"
    if "signed" in d.lower():                                            return "SIGNED_URL_INVALID"
    return {401: "MISSING_API_KEY", 403: "FORBIDDEN", 404: "FILE_NOT_FOUND",
            413: "FILE_TOO_LARGE"}.get(exc.status_code, "INTERNAL_ERROR")


async def _http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(status_code=exc.status_code,
                        content=ApiError(request_id=rid, error=str(exc.detail or ""),
                                         code=_error_code(exc)).model_dump())


async def _validation_exc_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = exc.errors()
    field = errors[0].get("loc", [""])[-1] if errors else None
    return JSONResponse(status_code=422,
                        content=ApiError(request_id=rid,
                                         error="Validation error — check request parameters",
                                         code=ErrorCode.INVALID_CATEGORY,
                                         detail=str(errors[0].get("msg", "")) if errors else None,
                                         field=str(field) if field else None).model_dump())


async def _global_exc_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(status_code=500,
                        content=ApiError(request_id=rid, error="Internal server error",
                                         code=ErrorCode.INTERNAL_ERROR,
                                         detail=str(exc) if not settings.is_production else None
                                         ).model_dump())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    for category in ["avatars", "kyc", "receipts"]:
        path = settings.upload_path / category
        path.mkdir(parents=True, exist_ok=True)
    await init_db()
    print(f"[STORAGEHUB] Storage Service started — env={settings.app_env}")
    print(f"[STORAGEHUB] Upload root: {settings.upload_path.resolve()}")
    yield
    print("[STORAGEHUB] Storage Service shutting down")


app = FastAPI(
    exception_handlers={
        HTTPException:          _http_exc_handler,
        RequestValidationError: _validation_exc_handler,
        Exception:              _global_exc_handler,
    },
    title="StorageHub — Secure Storage API",
    description=(
        "## API de stockage de fichiers sécurisée — multi-tenant SaaS\n\n"
        "### Authentification\n"
        "Tous les endpoints `/v1/` requièrent le header **`X-API-Key`**.\n\n"
        "En production, ajouter **`X-Timestamp`** et **`X-Signature`** (HMAC-SHA256).\n\n"
        "L'identité de l'utilisateur final est transmise via **`X-User-Id`** et **`X-User-Role`**.\n\n"
        "### Réponses\n"
        "Toutes les réponses suivent le contrat :\n"
        "```json\n{ \"success\": true, \"request_id\": \"uuid\", \"data\": {...} }\n```\n"
        "### Erreurs\n"
        "```json\n{ \"success\": false, \"request_id\": \"uuid\", \"error\": \"message\", \"code\": \"ERROR_CODE\" }\n```\n"
    ),
    version="1.0.0",
    contact={"name": "WIB Company — Engineering", "email": "tech@wibcompany.com"},
    # Swagger / ReDoc exposés uniquement en développement
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    openapi_tags=[
        {"name": "files",       "description": "Upload, download, suppression et métadonnées des fichiers"},
        {"name": "public",      "description": "Accès public aux avatars (sans authentification)"},
        {"name": "monitoring",  "description": "Santé du service, métriques disque, liveness probe"},
    ],
    lifespan=lifespan,
)

# ── CORS (allow_credentials=True incompatible avec wildcard — séparé par env)
if settings.is_production:
    app.add_middleware(CORSMiddleware, allow_origins=[settings.base_url],
                       allow_credentials=True, allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["X-Request-ID", "X-Service-Version"])
else:
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_credentials=False, allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["X-Request-ID", "X-Service-Version"])

# ── Routers
app.include_router(files.router)
app.include_router(accounts.router)
app.include_router(health.router)
app.include_router(public.router)

# ── UI statique
ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
if os.path.exists(ui_path):
    app.mount("/ui", StaticFiles(directory=ui_path, html=True), name="ui")


# ──────────────────────────────────────────────
#  Middleware — Request ID + headers de service
# ──────────────────────────────────────────────
@app.middleware("http")
async def add_integration_headers(request: Request, call_next):
    """
    Injecte sur chaque réponse :
    - X-Request-ID : identifiant unique de la requête (tracabilité)
    - X-Service-Version : version du service
    - X-Response-Time : temps de traitement en ms
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"]      = request_id
    response.headers["X-Service-Version"] = "1.0.0"
    response.headers["X-Response-Time"]   = f"{elapsed_ms}ms"
    # Désactiver le cache navigateur pour /ui en dev (évite de servir du JS périmé)
    if not settings.is_production and request.url.path.startswith("/ui"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


# ──────────────────────────────────────────────
#  Endpoints racine
# ──────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    """Landing page — présentation publique du service."""
    index = os.path.join(ui_path, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {
        "service": "StorageHub — Storage Service",
        "version": "1.0.0",
        "status": "running",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@app.get("/v1/ping", tags=["monitoring"], summary="Liveness probe — aucune auth requise")
async def ping():
    """
    Endpoint ultra-léger pour vérifier que le service répond.
    Pas de vérification DB ni disque — utilisé par load-balancers et orchestrateurs.
    """
    return {"pong": True, "version": "1.0.0", "service": "storagehub"}
