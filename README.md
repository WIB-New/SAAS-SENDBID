# StorageHub — StorageHub Storage Service

API de stockage de fichiers sécurisée, en mode **SaaS multi-tenant**. Chaque client
crée un compte, génère ses propres identifiants API (`api_key` + `hmac_secret`) et
intègre le stockage dans son application web, mobile ou backend.

**Production :** https://storagehub.aiforge.world
**Dashboard :** https://storagehub.aiforge.world/ui/dashboard.html
**Docs :** https://storagehub.aiforge.world/ui/docs.html · `/docs` (Swagger)

---

## Fonctionnalités

- **Comptes self-service** — inscription → credentials API générés instantanément
- **Dashboard client** — clés API (créer/révoquer), statistiques d'usage, plans
- **Auth service-to-service** — `X-API-Key` + `X-Timestamp` + `X-Signature` (HMAC-SHA256, anti-rejeu 30 s)
- **3 catégories** — `avatars` (public, cache CDN) · `kyc` et `receipts` (privés, audités)
- **Sécurité fichiers** — détection MIME par magic bytes, rejet exécutables, purge EXIF, anti path-traversal
- **URLs signées** — partage temporaire de fichiers sensibles, TTL plafonné par plan
- **Quotas par plan** — appliqués côté serveur à chaque upload
- **Audit trail** — journal PostgreSQL de chaque accès sensible (qui, IP, action)
- **Observabilité** — `/health`, `/v1/metrics` (Prometheus), `X-Request-ID` partout

## Plans

| Plan | Prix | Stockage | Clés API | TTL URL signée max |
|------|------|----------|----------|---------------------|
| Gratuit | 0 € | 500 MB | 1 | 60 s |
| Pro | 19 €/mois | 50 GB | 3 | 5 min |
| Business | 79 €/mois | 500 GB | 10 | 1 h |

## Quickstart

### 1. Obtenir des credentials

Via le dashboard (recommandé) ou l'API :

```bash
curl -X POST https://storagehub.aiforge.world/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"email":"vous@entreprise.com","password":"motdepasse","company_name":"Ma App"}'
# → {"api_key":"shk_…","hmac_secret":"…","access_token":"…"}
```

### 2. Uploader un fichier (Python)

```python
import hashlib, hmac, time, requests

BASE, KEY, SECRET = "https://storagehub.aiforge.world", "shk_…", "…"

ts = str(int(time.time()))
body_hash = hashlib.sha256(b"").hexdigest()   # corps vide pour multipart
sig = hmac.new(SECRET.encode(), f"{KEY}:{ts}:{body_hash}".encode(),
               hashlib.sha256).hexdigest()

r = requests.post(f"{BASE}/v1/files",
    files={"file": open("avatar.png", "rb")},
    data={"category": "avatars"},
    headers={"X-API-Key": KEY, "X-Timestamp": ts, "X-Signature": sig,
             "X-User-Id": "user-42"})
print(r.json()["url"])  # URL publique pour avatars
```

> **Multipart** : la signature couvre `sha256(b"")` — le corps multipart n'est
> pas inclus dans le message signé.

Guides complets (JavaScript, React Native, Flutter, Node.js, Django) :
**/ui/docs.html** — et client prêt à l'emploi : `django_integration/storage_client.py`.

## Architecture

```
Client web/mobile/serveur
        │  (HMAC-SHA256 signé)
        ▼
Traefik (HTTPS · Let's Encrypt)  ──► storagehub.aiforge.world
        │
        ▼
FastAPI :8080 ──► PostgreSQL managé (clients, clés, fichiers, audit)
        └─────► /var/app/uploads/{category}/{YYYY}/{MM}/{uuid}
```

## Stack & structure

```
app/
  main.py              FastAPI app, middleware, error handlers, landing page
  config.py            Settings (pydantic) + catalogue PLANS
  auth.py              AuthContext, HMAC, résolution clés DB, JWT dashboard
  database.py          SQLAlchemy async (SQLite dev / PostgreSQL prod)
  models.py            Client, ApiKey, StoredFile, AuditLog
  routers/files.py     Upload / download / signed URLs / delete / list
  routers/accounts.py  Register, login, keys, usage, plans (JWT)
  routers/public.py    Avatars publics (sans auth)
  routers/health.py    /health, /v1/metrics, /v1/info
  utils/               storage, file_validation, image_processing, audit, security
ui/
  index.html           Landing page (marketing, pricing)
  dashboard.html       Espace client (login, clés, usage, plans)
  docs.html            Documentation d'intégration multi-plateforme
django_integration/    Client Python pour le backend StorageHub
nginx/                 Conf Nginx de référence (prod hors Dokploy)
scripts/               backup (restic), monitoring disque, migration Emergent
tests/                 pytest — uploads, sécurité, contrôle d'accès
```

## Variables d'environnement (service)

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` (SQLite par défaut en dev) |
| `API_KEY` / `HMAC_SECRET` | Clé **maître** interne (admin, tests) — les clients ont leurs propres clés en DB |
| `HMAC_TIMESTAMP_TOLERANCE_SECONDS` | Fenêtre anti-rejeu (défaut 30) |
| `UPLOAD_ROOT` | Racine de stockage (`/var/app/uploads` en prod) |
| `MAX_SIZE_{AVATAR,KYC,RECEIPT}_MB` | Limites par catégorie |
| `SIGNED_URL_TTL` | TTL par défaut des URLs signées |
| `BASE_URL` / `CDN_BASE_URL` | Base publique pour les URLs générées |
| `DISK_ALERT_THRESHOLD_PERCENT` | Seuil d'alerte disque `/health` |

## Développement local

```bash
pip install -r requirements.txt
cp .env.example .env        # APP_ENV=development, SQLite par défaut
uvicorn app.main:app --reload --port 8080
# → http://localhost:8080          landing page
# → http://localhost:8080/docs     Swagger UI (dev uniquement — désactivé en prod)
# → http://localhost:8080/ui/dashboard.html
pytest                      # tests
```

## Déploiement (Dokploy)

Service `compose` (source `git` → `main`, `composePath: ./docker-compose.yml`),
domaine Traefik `storagehub.aiforge.world` → port 8080, HTTPS Let's Encrypt.
PostgreSQL : service managé Dokploy `storagehub-db` (volume persistant).

Env Dokploy : `DATABASE_URL`, `API_KEY`, `HMAC_SECRET`, `BASE_URL`, `CDN_BASE_URL`.

---

© 2026 WIB Company — StorageHub
