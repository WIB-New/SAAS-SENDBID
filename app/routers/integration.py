"""
StorageHub — Integration router
Endpoints destinés aux développeurs qui intègrent le service dans une application externe.

GET  /v1/integration/guide        Guide complet : plans, auth, exemples de code
GET  /v1/integration/status       Status temps réel visible depuis l'extérieur
POST /v1/integration/test         Test de connectivité + validation des credentials
GET  /v1/integration/openapi      Spec OpenAPI téléchargeable
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext, get_auth_context
from app.config import PLANS, settings
from app.database import get_db
from app import models

router = APIRouter(prefix="/v1/integration", tags=["integration"])


# ──────────────────────────────────────────────
#  GET /v1/integration/status — Health public (sans auth)
# ──────────────────────────────────────────────
@router.get("/status", summary="Status public du service (sans authentification)")
async def public_status(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Endpoint léger pour qu'une application externe vérifie que le service est joignable.
    Retourne version, status DB, liste des plans et URL publique.
    """
    db_ok = True
    try:
        await db.execute(select(func.count()).select_from(models.StoredFile))
    except Exception:
        db_ok = False

    base = str(request.base_url).rstrip("/")

    return {
        "service":     "StorageHub",
        "version":     "2.0.0",
        "status":      "operational" if db_ok else "degraded",
        "db":          "ok" if db_ok else "error",
        "timestamp":   datetime.utcnow().isoformat() + "Z",
        "public_url":  base,
        "plans":       {
            pid: {
                "name":           p["name"],
                "price_monthly_eur": p["price_monthly"],
                "storage_mb":     p["storage_mb"],
                "storage_label":  _fmt_mb(p["storage_mb"]),
            }
            for pid, p in PLANS.items()
        },
        "categories": ["avatars", "kyc", "receipts"],
        "docs_url":   f"{base}/docs" if not settings.is_production else None,
    }


# ──────────────────────────────────────────────
#  POST /v1/integration/test — Test credentials
# ──────────────────────────────────────────────
@router.post("/test", summary="Tester les credentials d'une application externe")
async def test_connection(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """
    Valide l'API key, retourne le profil du client et l'usage actuel.
    Utilisez cet endpoint pour vérifier que votre intégration fonctionne.
    """
    # Usage du client
    usage = await _get_usage(db, auth.client_id)

    plan = PLANS.get(auth.plan, PLANS["free"])
    quota_bytes = plan["storage_mb"] * 1024 * 1024
    used_pct = round(usage["total_bytes"] / quota_bytes * 100, 2) if quota_bytes else 0

    return {
        "success":     True,
        "message":     "Credentials valid — connection successful",
        "request_id":  getattr(request.state, "request_id", str(uuid.uuid4())),
        "timestamp":   datetime.utcnow().isoformat() + "Z",
        "client": {
            "client_id":  auth.client_id,
            "user_id":    auth.user_id,
            "role":       auth.role,
            "plan":       auth.plan,
            "plan_label": plan["name"],
            "is_admin":   auth.is_admin,
        },
        "quota": {
            "plan":           auth.plan,
            "storage_limit":  _fmt_mb(plan["storage_mb"]),
            "storage_used":   _fmt_bytes(usage["total_bytes"]),
            "storage_free":   _fmt_bytes(max(0, quota_bytes - usage["total_bytes"])),
            "used_percent":   used_pct,
            "files_count":    usage["total_files"],
            "alert":          used_pct >= 90,
        },
        "capabilities": {
            "upload_avatar": True,
            "upload_kyc":    True,
            "upload_receipt": True,
            "max_file_sizes": {
                "avatars":  f"{settings.max_size_avatar_mb} MB",
                "kyc":      f"{settings.max_size_kyc_mb} MB",
                "receipts": f"{settings.max_size_receipt_mb} MB",
            },
            "webhooks":  True,
            "signed_urls": True,
            "thumbnails": True,
            "encryption": True,
            "signed_url_max_ttl": f"{plan.get('signed_url_max_ttl', 60)}s",
        },
    }


# ──────────────────────────────────────────────
#  GET /v1/integration/guide — Guide complet
# ──────────────────────────────────────────────
@router.get("/guide", summary="Guide d'intégration complet avec exemples de code")
async def integration_guide(request: Request):
    """
    Retourne tout ce qu'un développeur externe a besoin pour intégrer StorageHub :
    plans, authentification, exemples curl/Python/JavaScript/PHP.
    """
    base = str(request.base_url).rstrip("/")
    api_key_example = "YOUR_API_KEY"

    return {
        "title":       "StorageHub Integration Guide",
        "version":     "2.0.0",
        "base_url":    base,
        "docs":        f"{base}/docs",

        # ── Plans ────────────────────────────────────────────────────────
        "plans": [
            {
                "id":             pid,
                "name":           p["name"],
                "price":          f"{p['price_monthly']}€/mois",
                "storage":        _fmt_mb(p["storage_mb"]),
                "max_api_keys":   p["max_keys"],
                "signed_url_ttl": f"{p['signed_url_max_ttl']}s max",
                "support":        p["support"],
                "register_url":   f"POST {base}/v1/accounts/register",
            }
            for pid, p in PLANS.items()
        ],

        # ── Authentification ─────────────────────────────────────────────
        "authentication": {
            "method":      "API Key via header X-API-Key",
            "dev_mode":    "Clé de test : dev-api-key-sendbid-2024",
            "production":  "Obtenez votre clé via POST /v1/accounts/register",
            "user_context": {
                "X-User-Id":   "Identifiant de votre utilisateur final (ex: user-123)",
                "X-User-Role": "Rôle : 'user' ou 'admin'",
            },
        },

        # ── Endpoints clés ───────────────────────────────────────────────
        "endpoints": {
            "register":        f"POST {base}/v1/accounts/register",
            "login":           f"POST {base}/v1/accounts/login",
            "upload":          f"POST {base}/v1/files",
            "upload_bulk":     f"POST {base}/v1/files/bulk",
            "upload_from_url": f"POST {base}/v1/files/from-url",
            "list_files":      f"GET  {base}/v1/files?page=1&limit=20",
            "download":        f"GET  {base}/v1/files/{{file_id}}",
            "signed_url":      f"GET  {base}/v1/files/{{file_id}}/signed",
            "thumbnail":       f"GET  {base}/v1/files/{{file_id}}/thumbnail",
            "delete":          f"DELETE {base}/v1/files/{{file_id}}",
            "webhook_create":  f"POST {base}/v1/webhooks",
            "quota":           f"GET  {base}/v1/accounts/usage",
            "stats":           f"GET  {base}/v1/accounts/stats",
            "test_connect":    f"POST {base}/v1/integration/test",
            "status":          f"GET  {base}/v1/integration/status",
        },

        # ── Catégories ───────────────────────────────────────────────────
        "categories": {
            "avatars":  {"public": True,  "max": f"{settings.max_size_avatar_mb} MB",  "types": ["JPEG","PNG","WebP"]},
            "kyc":      {"public": False, "max": f"{settings.max_size_kyc_mb} MB",     "types": ["JPEG","PNG","PDF"], "note": "Chiffré AES-256"},
            "receipts": {"public": False, "max": f"{settings.max_size_receipt_mb} MB", "types": ["JPEG","PNG","PDF"], "note": "Chiffré AES-256"},
        },

        # ── Exemples de code ─────────────────────────────────────────────
        "examples": {

            "step1_register": {
                "description": "1. Créer un compte → obtenir votre clé API",
                "curl": f"""curl -X POST {base}/v1/accounts/register \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"you@company.com","password":"SecurePass123","company_name":"My App"}}'""",
                "python": f"""import httpx

resp = httpx.post("{base}/v1/accounts/register", json={{
    "email": "you@company.com",
    "password": "SecurePass123",
    "company_name": "My App"
}})
creds = resp.json()
api_key = creds["api_key"]        # Conservez-le !
hmac_secret = creds["hmac_secret"] # Ne jamais exposer côté client""",
                "javascript": f"""const resp = await fetch("{base}/v1/accounts/register", {{
  method: "POST",
  headers: {{ "Content-Type": "application/json" }},
  body: JSON.stringify({{
    email: "you@company.com",
    password: "SecurePass123",
    company_name: "My App"
  }})
}});
const {{ api_key, hmac_secret }} = await resp.json();""",
            },

            "step2_upload_avatar": {
                "description": "2. Upload d'un avatar utilisateur",
                "curl": f"""curl -X POST {base}/v1/files \\
  -H "X-API-Key: {api_key_example}" \\
  -H "X-User-Id: user-123" \\
  -H "X-User-Role: user" \\
  -F "file=@photo.jpg" \\
  -F "category=avatars" \\
  -F 'tags={{"user_id":"123","app":"myapp"}}'""",
                "python": f"""import httpx

with open("photo.jpg", "rb") as f:
    resp = httpx.post(
        "{base}/v1/files",
        headers={{
            "X-API-Key": api_key,
            "X-User-Id": "user-123",
            "X-User-Role": "user",
        }},
        files={{"file": ("photo.jpg", f, "image/jpeg")}},
        data={{
            "category": "avatars",
            "tags": '{{"user_id":"123","app":"myapp"}}'
        }}
    )

result = resp.json()
avatar_url = result["url"]       # URL publique CDN
thumbnail  = result["thumbnail_url"]
file_id    = result["file_id"]""",
                "javascript": f"""const hub = new StorageHub({{ apiKey: api_key, baseUrl: "{base}" }});

const result = await hub.upload(file, "avatars", {{
  tags: {{ user_id: "123", app: "myapp" }}
}});

console.log(result.url);           // URL publique avatar
console.log(result.thumbnail_url); // Miniature 256x256""",
            },

            "step3_upload_kyc": {
                "description": "3. Upload KYC (document chiffré, privé)",
                "curl": f"""curl -X POST {base}/v1/files \\
  -H "X-API-Key: {api_key_example}" \\
  -H "X-User-Id: user-123" \\
  -F "file=@id_card.pdf" \\
  -F "category=kyc" \\
  -F 'tags={{"doc_type":"id_card","country":"FR"}}'""",
                "note": "Le fichier est chiffré AES-256 avant écriture. Jamais accessible publiquement.",
            },

            "step4_signed_url": {
                "description": "4. Générer une URL d'accès temporaire (60 secondes)",
                "curl": f"""# Générer l'URL signée
curl -H "X-API-Key: {api_key_example}" \\
  "{base}/v1/files/FILE_ID/signed?ttl=60"

# L'URL retournée peut être utilisée sans authentification
# pendant 60 secondes""",
                "python": f"""resp = httpx.get(
    f"{base}/v1/files/{{file_id}}/signed",
    headers={{"X-API-Key": api_key}},
    params={{"ttl": 60}}
)
signed_url = resp.json()["signed_url"]
# Partagez cette URL temporairement avec votre utilisateur""",
            },

            "step5_webhook": {
                "description": "5. Recevoir des notifications (webhook)",
                "curl": f"""curl -X POST {base}/v1/webhooks \\
  -H "X-API-Key: {api_key_example}" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "url": "https://myapp.com/webhooks/storage",
    "events": "file.uploaded,file.deleted",
    "secret": "my-webhook-secret"
  }}'""",
                "payload_example": {
                    "event":       "file.uploaded",
                    "occurred_at": "2026-10-15T10:00:00Z",
                    "data": {
                        "file_id":   "abc-123",
                        "category":  "kyc",
                        "size":      524288,
                    },
                },
                "signature_verification": {
                    "header": "X-StorageHub-Signature",
                    "format": "sha256=HMAC_HEX",
                    "python": """import hmac, hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)""",
                },
            },

            "sdk_usage": {
                "description": "6. Utiliser le SDK officiel",
                "python_install": "pip install httpx  # Le SDK est dans sdk/python/storagehub.py",
                "python": f"""from storagehub import StorageHub

hub = StorageHub(
    api_key="YOUR_API_KEY",
    base_url="{base}",
    user_id="user-123",
)

# Upload
result = hub.upload("photo.jpg", "avatars", tags={{"user": "123"}})

# Liste paginée
files = hub.list_files(category="avatars", page=1, limit=20)

# Stats
stats = hub.get_stats()
print(stats["total_size_bytes"], stats["uploads_by_day"])""",
                "javascript": f"""import {{ StorageHub }} from './sdk/javascript/storagehub.js';

const hub = new StorageHub({{
  apiKey: "YOUR_API_KEY",
  baseUrl: "{base}",
  userId: "user-123",
}});

// Upload fichier depuis <input type="file">
const result = await hub.upload(file, "avatars");

// Lister les fichiers
const {{ items, total }} = await hub.listFiles({{ category: "kyc" }});""",
            },
        },

        # ── Gestion des erreurs ──────────────────────────────────────────
        "error_handling": {
            "format": {"success": False, "code": "ERROR_CODE", "error": "message", "request_id": "uuid"},
            "codes": {
                "MISSING_API_KEY":   "Header X-API-Key manquant",
                "INVALID_API_KEY":   "Clé invalide ou révoquée",
                "QUOTA_EXCEEDED":    "Quota de stockage dépassé — passez au plan supérieur",
                "FILE_TOO_LARGE":    f"Fichier trop grand (max avatars={settings.max_size_avatar_mb}MB, kyc/receipts={settings.max_size_kyc_mb}MB)",
                "INVALID_MIME":      "Type de fichier non autorisé pour cette catégorie",
                "MALWARE_DETECTED":  "Fichier rejeté par le scan antivirus",
                "RATE_LIMIT_EXCEEDED": "Trop de requêtes — max 60 uploads/min",
                "SIGNED_URL_INVALID": "URL signée expirée ou invalide",
            },
        },
    }


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────
def _fmt_mb(mb: int) -> str:
    if mb >= 1024:
        return f"{mb // 1024} GB"
    return f"{mb} MB"


def _fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3:
        return f"{b / 1024**3:.2f} GB"
    if b >= 1024 ** 2:
        return f"{b / 1024**2:.2f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"


async def _get_usage(db: AsyncSession, client_id) -> dict:
    result = await db.execute(
        select(
            func.count(models.StoredFile.id),
            func.coalesce(func.sum(models.StoredFile.size_bytes), 0),
        ).where(
            models.StoredFile.client_id == client_id,
            models.StoredFile.is_deleted == False,
        )
    )
    row = result.one()
    return {"total_files": row[0], "total_bytes": row[1]}
