"""
SAAS SENDBID — Storage Service
FastAPI application entry point — prêt pour l'intégration
"""
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import files, health, public
from app.schemas import ApiError, ErrorCode

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    for category in ["avatars", "kyc", "receipts"]:
        path = settings.upload_path / category
        path.mkdir(parents=True, exist_ok=True)
    await init_db()
    print(f"[SENDBID] Storage Service started — env={settings.app_env}")
    print(f"[SENDBID] Upload root: {settings.upload_path.resolve()}")
    yield
    print("[SENDBID] Storage Service shutting down")


app = FastAPI(
    title="SAAS SENDBID — Storage Service",
    description=(
        "## Microservice de stockage local sécurisé — SendBID / PayBID\n\n"
        "### Authentification\n"
        "Tous les endpoints `/v1/` requièrent le header **`X-API-Key`**.\n\n"
        "En production, ajouter **`X-Timestamp`** et **`X-Signature`** (HMAC-SHA256).\n\n"
        "L'identité de l'utilisateur final est transmise via **`X-User-Id`** et **`X-User-Role`**.\n\n"
        "### Réponses\n"
        "Toutes les réponses suivent le contrat :\n"
        "```json\n{ \"success\": true, \"request_id\": \"uuid\", \"data\": {...} }\n```\n"
        "### Erreurs\n"
        "```json\n{ \"success\": false, \"request_id\": \"uuid\", \"error\": \"message\", \"code\": \"ERROR_CODE\" }\n```\n"
        "### Auth de test (dev)\n"
        "```\nX-API-Key: dev-api-key-sendbid-2024\nX-User-Id: user-001\nX-User-Role: user\n```"
    ),
    version="1.0.0",
    contact={"name": "WIB Company — Engineering", "email": "tech@wibcompany.com"},
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "files",       "description": "Upload, download, suppression et métadonnées des fichiers"},
        {"name": "public",      "description": "Accès public aux avatars (sans authentification)"},
        {"name": "monitoring",  "description": "Santé du service, métriques disque, liveness probe"},
    ],
    lifespan=lifespan,
)

# ── CORS
origins = ["*"] if not settings.is_production else [settings.base_url]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Service-Version"],
)

# ── Routers
app.include_router(files.router)
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
    return response


# ──────────────────────────────────────────────
#  Handlers d'erreur globaux
# ──────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = exc.errors()
    field = errors[0].get("loc", [""])[- 1] if errors else None
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
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


# ──────────────────────────────────────────────
#  Endpoints racine
# ──────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return {
        "service":  "SAAS SENDBID — Storage Service",
        "version":  "1.0.0",
        "status":   "running",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "endpoints": {
            "docs":    "/docs",
            "redoc":   "/redoc",
            "health":  "/health",
            "ping":    "/v1/ping",
            "metrics": "/v1/metrics",
            "ui":      "/ui",
        },
    }


@app.get("/v1/ping", tags=["monitoring"], summary="Liveness probe — aucune auth requise")
async def ping():
    """
    Endpoint ultra-léger pour vérifier que le service répond.
    Pas de vérification DB ni disque — utilisé par load-balancers et orchestrateurs.
    """
    return {"pong": True, "version": "1.0.0", "service": "sendbid-storage"}
