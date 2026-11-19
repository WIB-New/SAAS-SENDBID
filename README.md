# StorageHub — Storage as a Service

API de stockage de fichiers sécurisée en mode **SaaS multi-tenant** — un « mini-S3 »
clé en main. Chaque client crée un compte, obtient ses propres credentials API
(`api_key` + `hmac_secret`) et intègre le stockage dans son application web,
mobile ou backend. Ses utilisateurs finaux poussent leurs documents (photos de
profil, pièces d'identité, vidéos, archives…) ; StorageHub les stocke, les sécurise
et les redistribue.

**Production :** https://storagehub.aiforge.world
**Dashboard :** https://storagehub.aiforge.world/ui/dashboard.html
**Docs :** `/docs` (Swagger) · [API_REFERENCE.md](API_REFERENCE.md) · `GET /v1/integration/guide`

---

## Fonctionnalités

- **Comptes self-service** — inscription → credentials API générés instantanément
- **Dashboard client** — clés API (créer/révoquer), statistiques d'usage, plans
- **Auth service-to-service** — `X-API-Key` + `X-Timestamp` + `X-Signature` (HMAC-SHA256, anti-rejeu 30 s)
- **4 catégories** — `avatars` (public, cache CDN) · `kyc` et `receipts` (privés, chiffrés AES-256-GCM par tenant, audités) · `files` (générique : tout type sauf exécutables, privé)
- **Dossiers logiques** — champ `folder` sur chaque upload, arborescence via `GET /v1/files/folders`, filtres `?folder=` et `?q=`
- **Sécurité fichiers** — MIME par magic bytes, antivirus (EICAR/exécutables/PDF-JS), purge EXIF, anti path-traversal, lecture chunkée avec abort précoce
- **URLs signées** — partage temporaire de fichiers privés, TTL plafonné par plan, secret dédié dérivé
- **Quotas par plan** — stockage, taille fichier, rate limit, bulk, webhooks appliqués côté serveur
- **Webhooks** — livraison signée en tâche de fond, retries 0/2/10/30 s, historique des livraisons
- **Audit trail** — journal de chaque accès sensible (qui, IP, action), rétention configurable
- **Anti-SSRF** — `/from-url` bloque IPs privées/metadata cloud, redirections re-validées, **épinglage d'IP** anti DNS-rebinding
- **Stockage pluggable** — disque local ou **S3/R2/MinIO** (`STORAGE_BACKEND`)
- **Scalable** — rate limiting **Redis** optionnel (`REDIS_URL`), app stateless, Postgres en prod
- **Billing** — Stripe Checkout + webhook signé (optionnel, `STRIPE_*`)
- **Migrations** — Alembic (`alembic upgrade head`) + filets légers au démarrage
- **Observabilité** — `/health`, `/v1/metrics`, `/v1/info`, `X-Request-ID`

## Plans

| Plan | Prix | Stockage | Clés API | Fichier max | TTL signé | Extras |
|------|------|----------|----------|-------------|-----------|--------|
| Gratuit | 0 € | 500 MB | 1 | 5 MB | 60 s | 20 uploads/min |
| Starter | 5 €/mois | 2 GB | 2 | 10 MB | 2 min | Webhooks, 40/min |
| Pro | 19 €/mois | 50 GB | 5 | 25 MB | 5 min | Bulk upload, 60/min |
| Business | 79 €/mois | 500 GB | 20 | 100 MB | 1 h | 300/min, SLA |

Tout compte démarre en **Gratuit**. Upgrades : `POST /v1/billing/checkout`
(Stripe, si configuré) ou `POST /v1/admin/clients/{id}/plan` (master key).
Pas d'auto-upgrade direct — `POST /v1/accounts/plan` n'accepte que `free`.

## Quickstart

### 1. Créer un compte

```bash
curl -X POST https://storagehub.aiforge.world/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"email":"vous@entreprise.com","password":"motdepasse","company_name":"Ma App"}'
# → {"api_key":"shk_…","hmac_secret":"…","access_token":"…"}
```

### 2. Uploader (dev — clé seule)

```bash
# Avatar public → URL CDN immédiate
curl -X POST http://localhost:8000/v1/files \
  -H "X-API-Key: VOTRE_CLE" -H "X-User-Id: user-42" \
  -F "file=@photo.jpg" -F "category=avatars"

# Document générique dans un dossier logique
curl -X POST http://localhost:8000/v1/files \
  -H "X-API-Key: VOTRE_CLE" -H "X-User-Id: user-42" \
  -F "file=@contrat.pdf" -F "category=files" -F "folder=clients/2024"
```

### 3. Naviguer et télécharger

```bash
curl -H "X-API-Key: VOTRE_CLE" "http://localhost:8000/v1/files/folders"
curl -H "X-API-Key: VOTRE_CLE" "http://localhost:8000/v1/files?folder=clients/2024&q=contrat"
curl -H "X-API-Key: VOTRE_CLE" "http://localhost:8000/v1/files/{file_id}/signed?ttl=60"
```

En production, ajoutez `X-Timestamp` + `X-Signature` =
`HMAC_SHA256(hmac_secret, "{api_key}:{ts}:{sha256(body)}")` — le corps multipart
est signé comme `sha256(b"")`. Guides multi-plateformes : `GET /v1/integration/guide`
et SDKs dans `sdk/` (Python, JavaScript) + `django_integration/`.

## Architecture

```
Apps clientes (web/mobile/backend)
        │  X-API-Key (+ HMAC en prod)
        ▼
Traefik/Nginx (HTTPS, cache CDN pour avatars publics)
        ▼
FastAPI (stateless, ×N instances)
   ├────► PostgreSQL  — clients, clés, métadonnées, audit, webhooks
   ├────► Stockage    — disque local OU S3/R2/MinIO (STORAGE_BACKEND)
   └────► Redis       — rate limiting distribué (optionnel, REDIS_URL)
```

Fichiers stockés sous `{category}/{YYYY}/{MM}/{uuid}` — jamais de chemin client.

## Structure

```
app/
  main.py              FastAPI app, middleware, handlers d'erreurs
  config.py            Settings pydantic + catalogue PLANS
  auth.py              AuthContext, HMAC, clés DB, JWT dashboard
  database.py          SQLAlchemy async + migrations légères
  models.py            Client, ApiKey, StoredFile, AuditLog, Webhook(+Delivery)
  ratelimit.py         Rate limiting (mémoire ou Redis)
  routers/files.py     Upload/bulk/from-url, dossiers, stream, signed, versions
  routers/accounts.py  Register/login/clés/usage/stats/plan
  routers/webhooks.py  CRUD webhooks + livraison en tâche de fond
  routers/billing.py   Stripe checkout + webhook (optionnel)
  routers/admin.py     Vue d'ensemble + gestion clients (master key)
  routers/public.py    Avatars publics
  routers/health.py    /health, /v1/metrics, /v1/info
  routers/integration.py  Guide d'intégration + test de connexion
  utils/               storage, backends (local/S3), encryption (AES-256-GCM),
                       file_validation, url_safety (SSRF), thumbnails, security
  tasks/purge.py       Purge fichiers + rétention audit (APScheduler)
alembic/               Migrations Alembic (env + baseline)
ui/                    Landing, dashboard, docs, integration, page de test
sdk/                   Clients Python et JavaScript
tests/                 pytest — 54 tests (uploads, sécurité, accès, plans, limites)
```

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `APP_ENV` | `development` (auth souple, /docs) ou `production` | development |
| `DATABASE_URL` | `postgresql+asyncpg://…` (SQLite si absent) | sqlite local |
| `API_KEY` / `HMAC_SECRET` | Clé **maître** interne (admin) | dev keys |
| `ENCRYPTION_KEY` | Clé de chiffrement des documents sensibles | dev key |
| `UPLOAD_ROOT` | Racine de stockage local | `./uploads` |
| `MAX_SIZE_{AVATAR,KYC,RECEIPT,FILE}_MB` | Limites par catégorie | 5/10/10/100 |
| `SIGNED_URL_TTL` | TTL par défaut des URLs signées | 60 |
| `BASE_URL` / `CDN_BASE_URL` | Bases des URLs générées | localhost |
| `STORAGE_BACKEND` | `local` ou `s3` | local |
| `S3_*` | Bucket, endpoint, clés, région, `S3_PUBLIC_BASE_URL` | — |
| `REDIS_URL` | Rate limiting distribué (optionnel) | mémoire |
| `AUDIT_RETENTION_DAYS` | Rétention des logs d'audit | 365 |
| `STRIPE_*` | `SECRET_KEY`, `WEBHOOK_SECRET`, `PRICE_{STARTER,PRO,BUSINESS}` | inactif |
| `VIRUSTOTAL_API_KEY` | Scan hash optionnel | désactivé |
| `DISK_ALERT_THRESHOLD_PERCENT` | Seuil d'alerte disque `/health` | 80 |

## Développement local

```bash
pip install -r requirements.txt
cp .env.example .env          # APP_ENV=development, SQLite par défaut
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000             landing page
# → http://localhost:8000/docs        Swagger UI (dev uniquement)
# → http://localhost:8000/test        page de test interactive
# → http://localhost:8000/ui/dashboard.html
pytest tests                        # 54 tests
alembic upgrade head                # migrations (optionnel — auto en dev)
```

En dev, `X-API-Key` seule suffit (la clé `API_KEY` du `.env` ou une clé client
`shk_…`). En production, la signature HMAC est exigée.

## Déploiement (Dokploy)

Service `compose` (source `git` → `walter`, `composePath: ./docker-compose.yml`),
domaine Traefik `storagehub.aiforge.world` → port 8080, HTTPS Let's Encrypt.
PostgreSQL managé + volume `uploads_data` (ou `STORAGE_BACKEND=s3` + R2/MinIO).

Env prod : `APP_ENV=production`, `DATABASE_URL`, `API_KEY`, `HMAC_SECRET`,
`ENCRYPTION_KEY`, `BASE_URL`, `CDN_BASE_URL` (+ `REDIS_URL`, `S3_*`, `STRIPE_*`).

---

© 2026 WIB Company — StorageHub
