# StorageHub — Référence API v2.0

Base URL : `http://localhost:8080` (local) · URL publique via `start_public.py`

## Authentification

Toutes les requêtes authentifiées utilisent ces headers :

| Header | Description |
|--------|-------------|
| `X-API-Key` | Clé client (`shk_…`) ou clé master (`dev-api-key-sendbid-2024` en dev) |
| `X-User-Id` | Identifiant de l'utilisateur final (ex: `user-123`) |
| `X-User-Role` | `user` ou `admin` |
| `X-Timestamp` | [Mode HMAC] Timestamp Unix |
| `X-Signature` | [Mode HMAC] Signature SHA256 |
| `Authorization` | `Bearer <JWT>` pour les endpoints dashboard |

---

## Enveloppe de réponse

```json
// Succès — format standard
{ "success": true, "request_id": "uuid", "data": { ... } }

// Erreur — format standard
{
  "success":    false,
  "request_id": "uuid",
  "error":      "Missing or invalid Authorization header",
  "code":       "MISSING_API_KEY",
  "detail":     null,
  "field":      null
}
```

### Codes d'erreur

| Code | HTTP | Description |
|------|------|-------------|
| `MISSING_API_KEY` | 401 | Header X-API-Key absent |
| `INVALID_API_KEY` | 401/403 | Clé invalide ou révoquée |
| `INVALID_CLIENT_KEY` | 401 | Clé client inconnue en DB |
| `MASTER_KEY_NO_CLIENT` | 403 | Clé master utilisée sur un endpoint client |
| `INVALID_HMAC` | 403 | Signature HMAC invalide/expirée |
| `ACCESS_DENIED` | 403 | Pas le propriétaire de la ressource |
| `FORBIDDEN` | 403 | Accès interdit (compte suspendu…) |
| `QUOTA_EXCEEDED` | 413 | Quota de stockage dépassé |
| `FILE_TOO_LARGE` | 413 | Fichier trop grand |
| `EMPTY_FILE` | 400 | Fichier vide |
| `INVALID_MIME` | 400 | Type MIME non autorisé |
| `INVALID_CATEGORY` | 400 | Catégorie inconnue |
| `DANGEROUS_FILE` | 400 | Exécutable/script rejeté |
| `MALWARE_DETECTED` | 400 | Menace détectée (EICAR, VirusTotal) |
| `FILE_NOT_FOUND` | 404 | Fichier introuvable |
| `SIGNED_URL_INVALID` | 403 | URL signée invalide ou expirée |
| `RATE_LIMIT_EXCEEDED` | 429 | Trop de requêtes |
| `INTERNAL_ERROR` | 500 | Erreur serveur |

---

## Monitoring

### `GET /health` — Readiness probe

```json
// RESPONSE 200
{
  "status":         "ok",           // "ok" | "degraded"
  "version":        "1.0.0",
  "env":            "development",
  "uptime_seconds": 3600.5,
  "db":             "ok",
  "disk_usage": {
    "total_gb": 500.0, "used_gb": 120.5, "free_gb": 379.5,
    "percent": 24.1, "alert": false
  },
  "categories": {
    "avatars":  { "size_mb": 12.3, "file_count": 45 },
    "kyc":      { "size_mb": 0.0,  "file_count": 0  },
    "receipts": { "size_mb": 0.0,  "file_count": 0  }
  },
  "checks": {
    "database":     { "status": "ok" },
    "disk":         { "status": "ok", "percent": 24.1 },
    "dir_avatars":  { "status": "ok" },
    "dir_kyc":      { "status": "ok" },
    "dir_receipts": { "status": "ok" }
  }
}
```

### `GET /v1/ping` — Liveness probe

```json
{ "pong": true, "version": "2.0.0", "service": "storagehub" }
```

### `GET /v1/metrics` — Métriques Prometheus (`text/plain`)

```text
storagehub_disk_used_gb 120.5
storagehub_disk_free_gb 379.5
storagehub_disk_percent_used 24.1
storagehub_uptime_seconds 3600.5
storagehub_category_size_mb{category="avatars"} 12.3
storagehub_category_file_count{category="avatars"} 45
```

### `GET /v1/info` — Informations de service

```json
{
  "service": "storagehub",
  "version": "1.0.0",
  "env":     "development",
  "categories": {
    "avatars":  { "public": true,  "max_size_mb": 5,  "allowed_mimes": ["image/jpeg","image/png","image/webp"] },
    "kyc":      { "public": false, "max_size_mb": 10, "allowed_mimes": ["image/jpeg","image/png","application/pdf"] },
    "receipts": { "public": false, "max_size_mb": 10, "allowed_mimes": ["image/jpeg","image/png","application/pdf"] }
  },
  "signed_url_default_ttl_seconds": 60,
  "cdn_base_url": "http://localhost:8080",
  "auth": {
    "required_header":  "X-API-Key",
    "hmac_header":      "X-Signature",
    "timestamp_header": "X-Timestamp",
    "user_id_header":   "X-User-Id",
    "user_role_header": "X-User-Role",
    "hmac_required_in_production": true
  },
  "response_envelope": {
    "success_shape": { "success": true, "request_id": "uuid", "data": "..." },
    "error_shape":   { "success": false, "request_id": "uuid", "error": "msg", "code": "CODE" }
  }
}
```

---

## Comptes

### `GET /v1/plans` — Catalogue des plans (public, sans auth)

```json
{
  "free":     { "name": "Gratuit",  "price_monthly_eur": 0,  "storage_mb": 500,    "max_keys": 1,  "signed_url_max_ttl": 60,   "support": "Community" },
  "starter":  { "name": "Starter",  "price_monthly_eur": 5,  "storage_mb": 2048,   "max_keys": 2,  "signed_url_max_ttl": 120,  "support": "Email" },
  "pro":      { "name": "Pro",      "price_monthly_eur": 19, "storage_mb": 51200,  "max_keys": 3,  "signed_url_max_ttl": 300,  "support": "Email 24h" },
  "business": { "name": "Business", "price_monthly_eur": 79, "storage_mb": 512000, "max_keys": 10, "signed_url_max_ttl": 3600, "support": "Prioritaire + SLA" }
}
```

### `POST /v1/accounts/register` — Créer un compte

```json
// REQUEST
{
  "email":        "you@company.com",
  "password":     "SecurePass123",      // min 8 caractères
  "company_name": "My App",             // optionnel
  "plan":         "starter"             // optionnel : free|starter|pro|business
}

// RESPONSE 201
{
  "client_id":    "uuid",
  "email":        "you@company.com",
  "plan":         "starter",
  "plan_details": {
    "name": "Starter", "price_monthly": 5, "storage_mb": 2048,
    "max_keys": 2, "signed_url_max_ttl": 120, "support": "Email",
    "upload_rate": 100, "max_file_size_mb": 10,
    "webhooks": true, "encryption": true, "bulk_upload": false
  },
  "api_key":      "shk_abc123...",      // Affiché UNE SEULE FOIS
  "hmac_secret":  "abc123...",          // Affiché UNE SEULE FOIS
  "access_token": "jwt...",
  "token_type":   "bearer",
  "storage_quota": "2048 MB",
  "warning":      "Conservez ces credentials en lieu sûr — le secret ne sera plus affiché."
}
```

**Erreurs :** `400` email invalide · `409` email déjà existant

### `POST /v1/accounts/login` — Connexion dashboard

```json
// REQUEST
{ "email": "you@company.com", "password": "SecurePass123" }

// RESPONSE 200
{
  "access_token": "jwt...",
  "token_type":   "bearer",
  "client": { "id": "uuid", "email": "you@company.com", "plan": "starter" }
}
```

**Erreurs :** `401` credentials invalides · `403` compte désactivé

### `GET /v1/accounts/me` — Profil + usage

**Auth :** `Authorization: Bearer <jwt>`

```json
{
  "id":           "uuid",
  "email":        "you@company.com",
  "company_name": "My App",
  "plan":         "starter",
  "plan_details": { "name": "Starter", "price_monthly": 5, "storage_mb": 2048, "max_keys": 2, "signed_url_max_ttl": 120, "support": "Email" },
  "created_at":   "2026-10-15T10:00:00",
  "usage": {
    "total_bytes":  524288,
    "total_files":  3,
    "by_category": {
      "avatars": { "files": 2, "bytes": 300000 },
      "kyc":     { "files": 1, "bytes": 224288 }
    },
    "storage_limit_bytes":  2147483648,
    "storage_used_percent": 0.02
  },
  "api_keys": [
    {
      "id":           "uuid",
      "name":         "Clé principale",
      "api_key":      "shk_abc1…xyz4",     // masqué
      "hmac_secret":  "••••••••",
      "plan":         "starter",
      "revoked":      false,
      "created_at":   "2026-10-15T10:00:00",
      "last_used_at": "2026-10-15T12:00:00"
    }
  ]
}
```

### `POST /v1/accounts/keys` — Nouvelle clé API

**Auth :** `Authorization: Bearer <jwt>`

```json
// REQUEST
{ "name": "Ma clé de prod" }

// RESPONSE 201
{
  "id":           "uuid",
  "name":         "Ma clé de prod",
  "api_key":      "shk_abc123...",     // Affiché UNE SEULE FOIS
  "hmac_secret":  "abc123...",         // Affiché UNE SEULE FOIS
  "plan":         "starter",
  "revoked":      false,
  "created_at":   "2026-10-15T10:00:00",
  "last_used_at": null,
  "warning":      "Le hmac_secret n'est affiché qu'une seule fois."
}
```

**Erreur :** `403` — limite `max_keys` du plan atteinte

### `DELETE /v1/accounts/keys/{key_id}` — Révoquer une clé

```json
{ "id": "uuid", "revoked": true }
```

### `POST /v1/accounts/plan` — Changer de plan

**Auth :** `Authorization: Bearer <jwt>`

```json
// REQUEST
{ "plan": "pro" }

// RESPONSE 200
{
  "plan": "pro",
  "plan_details": { "name": "Pro", "price_monthly": 19, "storage_mb": 51200, "max_keys": 3, "signed_url_max_ttl": 300, "support": "Email 24h" }
}
```

### `GET /v1/accounts/usage` — Quota temps réel

**Auth :** `X-API-Key` (clé client) **ou** `Bearer <jwt>`

```json
{
  "plan":          "starter",
  "plan_name":     "Starter",
  "price_monthly": "5€/mois",

  "storage": {
    "used_bytes":   524288,
    "used_label":   "512.0 KB",
    "quota_bytes":  2147483648,
    "quota_label":  "2.00 GB",
    "free_bytes":   2146959360,
    "free_label":   "2.00 GB",
    "used_percent": 0.02
  },

  "files":         3,
  "max_file_size": "10 MB",
  "max_api_keys":  2,
  "webhooks":      true,
  "encryption":    true,
  "bulk_upload":   false,

  "alerts": {
    "quota_warning":  false,   // true si >= 80%
    "quota_critical": false,   // true si >= 95%
    "quota_full":     false,   // true si 100%
    "message":        null     // "Attention : 85% du quota utilisé." si warning
  },

  "upgrade": {
    "available":   true,
    "next_plan":   "Pro",
    "next_price":  "19€/mois",
    "next_quota":  "50.00 GB",
    "upgrade_url": "POST /v1/accounts/plan"
  }
}
```

**Erreurs :** `403 MASTER_KEY_NO_CLIENT` (clé master) · `401 INVALID_CLIENT_KEY` · `401 MISSING_API_KEY`

### `GET /v1/accounts/stats` — Statistiques analytiques

**Auth :** `X-API-Key` ou `Bearer <jwt>` · **Params :** `?date_from=2026-10-01&date_to=2026-10-15`

```json
{
  "total_files":      5,
  "active_files":     4,
  "deleted_files":    1,
  "total_size_bytes": 1048576,
  "by_category": {
    "avatars":  { "count": 3, "size_bytes": 700000 },
    "kyc":      { "count": 1, "size_bytes": 300000 },
    "receipts": { "count": 0, "size_bytes": 0 }
  },
  "uploads_by_day": [
    { "date": "2026-10-15", "count": 3, "size_bytes": 500000 },
    { "date": "2026-10-14", "count": 2, "size_bytes": 300000 }
  ],
  "encrypted_files":  1,
  "thumbnail_count":  3,
  "plan":            "starter",
  "plan_details":    { "name": "Starter", "price_monthly": 5, "storage_mb": 2048 }
}
```

---

## Fichiers

### `POST /v1/files` — Upload

**Content-Type :** `multipart/form-data` · **Auth :** `X-API-Key` + `X-User-Id`

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `file` | binary | ✅ | Fichier à uploader |
| `category` | string | ✅ | `avatars` \| `kyc` \| `receipts` |
| `owner_user_id` | string | ❌ | Surcharge X-User-Id |
| `tags` | JSON string | ❌ | `{"user_id":"123","app":"myapp"}` |
| `replaces_file_id` | UUID | ❌ | Crée une nouvelle version |

```json
// RESPONSE 201
{
  "file_id":       "uuid",
  "category":      "avatars",
  "size":          86381,
  "mime":          "image/jpeg",
  "checksum":      "sha256hex...",
  "url":           "http://localhost:8080/v1/public/avatars/uuid",  // avatars seulement
  "thumbnail_url": "http://localhost:8080/v1/files/uuid/thumbnail",
  "public":        true,                                             // true si avatars
  "version":       1,
  "message":       "Upload successful"
}
```

### `POST /v1/files/bulk` — Upload multiple

**Content-Type :** `multipart/form-data`

| Champ | Type | Description |
|-------|------|-------------|
| `files` | binary[] | Plusieurs fichiers |
| `category` | string | `avatars` \| `kyc` \| `receipts` |
| `tags` | JSON string | Optionnel |

```json
// RESPONSE 201
{
  "uploaded": 4,
  "failed":   1,
  "results": [
    {
      "filename":      "photo1.jpg",
      "success":       true,
      "file_id":       "uuid",
      "url":           "http://...",
      "thumbnail_url": "http://..."
    },
    {
      "filename": "virus.exe",
      "success":  false,
      "error":    "File rejected: dangerous file"
    }
  ]
}
```

### `POST /v1/files/from-url` — Importer depuis une URL

```json
// REQUEST
{
  "url":      "https://example.com/photo.jpg",
  "category": "avatars",
  "tags":     { "source": "external_import" }   // optionnel
}

// RESPONSE 201 — identique à POST /v1/files
```

### `GET /v1/files` — Liste paginée

**Params :** `?page=1&limit=20&sort=created_at:desc&category=avatars`
**Sort :** `created_at` \| `size_bytes` \| `mime_type` \| `category` (+ `:asc` ou `:desc`)

```json
// RESPONSE 200
{
  "items": [
    {
      "file_id":         "uuid",
      "owner_user_id":   "user-123",
      "category":        "avatars",
      "mime_type":       "image/jpeg",
      "size_bytes":      86381,
      "checksum_sha256": "sha256hex...",
      "created_at":      "2026-10-15T10:00:00",
      "is_deleted":      false,
      "is_public":       true,
      "url":             "http://.../v1/public/avatars/uuid",
      "thumbnail_url":   "http://.../v1/files/uuid/thumbnail",
      "tags":            { "user_id": "123" },
      "version":         1,
      "parent_id":       null,
      "is_encrypted":    false
    }
  ],
  "total": 42,
  "page":  1,
  "limit": 20,
  "pages": 3
}
```

### `GET /v1/files/{file_id}` — Télécharger (auth requise)

**Response :** stream binaire · **Headers :** `Content-Type: <mime>`, `Content-Length: <bytes>`

### `GET /v1/files/{file_id}/meta` — Métadonnées

**Response :** objet `FileMetaResponse` identique à `items[]` dans `GET /v1/files`

### `GET /v1/files/{file_id}/thumbnail` — Miniature JPEG 256×256

**Response :** stream `image/jpeg` · **Headers :** `Cache-Control: public, max-age=86400`

### `PATCH /v1/files/{file_id}/tags` — Mettre à jour les tags

```json
// REQUEST
{ "tags": { "user_id": "456", "status": "verified" } }

// RESPONSE 200 — FileMetaResponse complet
```

### `GET /v1/files/{file_id}/signed` — URL signée

**Params :** `?ttl=60` (max selon plan : free=60s, starter=120s, pro=300s, business=3600s)

```json
// RESPONSE 200
{
  "file_id":     "uuid",
  "signed_url":  "http://localhost:8080/v1/files/uuid/download?expires=1728...&sig=abc...",
  "expires_at":  "2026-10-15T10:01:00",
  "ttl_seconds": 60,
  "method":      "GET"
}
```

### `GET /v1/files/{file_id}/download` — Via URL signée (sans auth)

**Params :** `?expires=<unix_ts>&sig=<hmac>` · **Response :** stream binaire · **Erreur :** `403` URL invalide/expirée

### `POST /v1/files/{file_id}/replace` — Nouvelle version

**Content-Type :** `multipart/form-data` · **Field :** `file`

```json
// RESPONSE 201 — FileUploadResponse avec version=2
```

### `GET /v1/files/{file_id}/versions` — Historique des versions

```json
// RESPONSE 200
[
  { "file_id": "uuid-v1", "version": 1, "size_bytes": 80000, "created_at": "...", "parent_id": null },
  { "file_id": "uuid-v2", "version": 2, "size_bytes": 86381, "created_at": "...", "parent_id": "uuid-v1" }
]
```

### `DELETE /v1/files/{file_id}` — Suppression logique

```json
// RESPONSE 200
{ "file_id": "uuid", "deleted": true, "message": "File marked for deletion" }
```

### `GET /v1/public/avatars/{file_id}` — Avatar public (sans auth)

**Response :** stream `image/jpeg` · **Headers :** `Cache-Control: public, max-age=31536000, immutable`

---

## Webhooks

### `POST /v1/webhooks` — Enregistrer un webhook

```json
// REQUEST
{
  "url":    "https://myapp.com/webhooks/storage",
  "events": "file.uploaded,file.deleted",   // ou "*" pour tous
  "secret": "my-webhook-secret"             // optionnel, pour signature HMAC
}

// RESPONSE 201
{
  "id":         "uuid",
  "url":        "https://myapp.com/webhooks/storage",
  "events":     "file.uploaded,file.deleted",
  "is_active":  true,
  "created_at": "2026-10-15T10:00:00"
}
```

### `GET /v1/webhooks` — Lister ses webhooks

```json
// RESPONSE 200
[
  { "id": "uuid", "url": "https://...", "events": "*", "is_active": true, "created_at": "..." }
]
```

### `DELETE /v1/webhooks/{id}` — Supprimer

```json
{ "id": "uuid", "deleted": true }
```

### `GET /v1/webhooks/{id}/deliveries` — Historique des livraisons

```json
// RESPONSE 200
[
  {
    "id":              1,
    "webhook_id":      "uuid",
    "event":           "file.uploaded",
    "response_status": 200,
    "success":         true,
    "error":           null,
    "attempted_at":    "2026-10-15T10:00:00"
  }
]
```

### Payload envoyé à votre endpoint webhook

```http
POST https://myapp.com/webhooks/storage
Content-Type: application/json
X-StorageHub-Event: file.uploaded
X-Delivery-ID: uuid
X-StorageHub-Signature: sha256=<HMAC_HEX>   (si secret configuré)
```

```json
{
  "event":       "file.uploaded",
  "occurred_at": "2026-10-15T10:00:00Z",
  "data": {
    "file_id":  "uuid",
    "category": "avatars",
    "size":     86381
  }
}
```

**Vérification de la signature (Python) :**

```python
import hmac, hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

---

## Intégration

### `GET /v1/integration/status` — Status public (sans auth)

```json
// RESPONSE 200
{
  "service":    "StorageHub",
  "version":    "2.0.0",
  "status":     "operational",
  "db":         "ok",
  "timestamp":  "2026-10-15T10:00:00Z",
  "public_url": "http://localhost:8080",
  "plans": {
    "free":     { "name": "Gratuit",  "price_monthly_eur": 0,  "storage_mb": 500,    "storage_label": "500 MB" },
    "starter":  { "name": "Starter",  "price_monthly_eur": 5,  "storage_mb": 2048,   "storage_label": "2 GB" },
    "pro":      { "name": "Pro",      "price_monthly_eur": 19, "storage_mb": 51200,  "storage_label": "50 GB" },
    "business": { "name": "Business", "price_monthly_eur": 79, "storage_mb": 512000, "storage_label": "500 GB" }
  },
  "categories": ["avatars", "kyc", "receipts"],
  "docs_url":   "http://localhost:8080/docs"
}
```

### `POST /v1/integration/test` — Test credentials

**Auth :** `X-API-Key` + `X-User-Id`

```json
// RESPONSE 200
{
  "success":    true,
  "message":    "Credentials valid — connection successful",
  "request_id": "uuid",
  "timestamp":  "2026-10-15T10:00:00Z",
  "client": {
    "client_id": "uuid",
    "user_id":   "user-123",
    "role":      "user",
    "plan":      "starter",
    "plan_label": "Starter",
    "is_admin":  false
  },
  "quota": {
    "plan":          "starter",
    "storage_limit": "2 GB",
    "storage_used":  "512.0 KB",
    "storage_free":  "2.00 GB",
    "used_percent":  0.02,
    "files_count":   3,
    "alert":         false
  },
  "capabilities": {
    "upload_avatar":  true,
    "upload_kyc":     true,
    "upload_receipt": true,
    "max_file_sizes": { "avatars": "5 MB", "kyc": "10 MB", "receipts": "10 MB" },
    "webhooks":       true,
    "signed_urls":    true,
    "thumbnails":     true,
    "encryption":     true,
    "signed_url_max_ttl": "120s"
  }
}
```

### `GET /v1/integration/guide` — Guide complet

```json
// RESPONSE 200
{
  "title":    "StorageHub Integration Guide",
  "version":  "2.0.0",
  "base_url": "http://localhost:8080",
  "docs":     "http://localhost:8080/docs",
  "plans": [
    { "id": "free", "name": "Gratuit", "price": "0€/mois", "storage": "500 MB", "max_api_keys": 1, "signed_url_ttl": "60s max", "support": "Community", "register_url": "POST .../register" }
  ],
  "authentication": {
    "method":      "API Key via header X-API-Key",
    "dev_mode":    "Clé de test : dev-api-key-sendbid-2024",
    "user_context": { "X-User-Id": "…", "X-User-Role": "…" }
  },
  "endpoints": {
    "register":        "POST {base}/v1/accounts/register",
    "upload":          "POST {base}/v1/files",
    "upload_bulk":     "POST {base}/v1/files/bulk",
    "upload_from_url": "POST {base}/v1/files/from-url",
    "list_files":      "GET  {base}/v1/files?page=1&limit=20",
    "download":        "GET  {base}/v1/files/{file_id}",
    "signed_url":      "GET  {base}/v1/files/{file_id}/signed",
    "thumbnail":       "GET  {base}/v1/files/{file_id}/thumbnail",
    "delete":          "DELETE {base}/v1/files/{file_id}",
    "webhook_create":  "POST {base}/v1/webhooks",
    "quota":           "GET  {base}/v1/accounts/usage",
    "stats":           "GET  {base}/v1/accounts/stats",
    "test_connect":    "POST {base}/v1/integration/test",
    "status":          "GET  {base}/v1/integration/status"
  },
  "categories": {
    "avatars":  { "public": true,  "max": "5 MB",  "types": ["JPEG","PNG","WebP"] },
    "kyc":      { "public": false, "max": "10 MB", "types": ["JPEG","PNG","PDF"], "note": "Chiffré AES-256" },
    "receipts": { "public": false, "max": "10 MB", "types": ["JPEG","PNG","PDF"], "note": "Chiffré AES-256" }
  },
  "examples": {
    "step1_register":      { "description": "…", "curl": "…", "python": "…", "javascript": "…" },
    "step2_upload_avatar": { "description": "…", "curl": "…", "python": "…", "javascript": "…" },
    "step3_upload_kyc":    { "description": "…", "curl": "…", "note": "Chiffré AES-256" },
    "step4_signed_url":    { "description": "…", "curl": "…", "python": "…" },
    "step5_webhook":       { "description": "…", "curl": "…", "payload_example": {…}, "signature_verification": {…} },
    "sdk_usage":           { "description": "…", "python": "…", "javascript": "…" }
  },
  "error_handling": {
    "format": { "success": false, "code": "CODE", "error": "msg", "request_id": "uuid" },
    "codes": { "MISSING_API_KEY": "...", "QUOTA_EXCEEDED": "...", "..." : "..." }
  }
}
```

---

## Admin — master key uniquement

**Auth :** `X-API-Key: dev-api-key-sendbid-2024` (clé master `.env`)

### `GET /v1/admin/overview` — Vue globale

```json
// RESPONSE 200
{
  "service":      "StorageHub",
  "version":      "2.0.0",
  "uptime_hours": 2.5,
  "timestamp":    "2026-10-15T10:00:00Z",

  "clients": {
    "total":    5,
    "active":   5,
    "inactive": 0,
    "by_plan":  { "free": 4, "starter": 1 }
  },

  "storage": {
    "total_files":           8,
    "total_size_bytes":      1048576,
    "total_size_label":      "1.00 MB",
    "deleted_pending_purge": 1,
    "disk_total":            500.0,
    "disk_used_pct":         24.1,
    "disk_alert":            false
  },

  "activity": {
    "uploads_last_24h": 3,
    "active_webhooks":  2
  },

  "revenue": {
    "mrr_eur":   5,
    "mrr_label": "5€/mois (estimé)",
    "note":      "Basé sur les plans actifs — sans passerelle de paiement"
  }
}
```

### `GET /v1/admin/clients` — Liste clients

**Params :** `?page=1&limit=20&plan=starter`

```json
// RESPONSE 200
{
  "items": [
    {
      "id":           "uuid",
      "email":        "you@company.com",
      "company_name": "My App",
      "plan":         "starter",
      "plan_name":    "Starter",
      "is_active":    true,
      "created_at":   "2026-10-15T10:00:00",
      "files":        3,
      "bytes_used":   524288,
      "bytes_label":  "512.0 KB",
      "quota_pct":    0.02
    }
  ],
  "total": 5, "page": 1, "limit": 20, "pages": 1
}
```

### `GET /v1/admin/clients/{client_id}` — Détail client

```json
// RESPONSE 200
{
  "id":           "uuid",
  "email":        "you@company.com",
  "company_name": "My App",
  "plan":         "starter",
  "plan_details": { "name": "Starter", "price_monthly": 5, "storage_mb": 2048, "max_keys": 2 },
  "is_active":    true,
  "created_at":   "2026-10-15T10:00:00",
  "storage": {
    "used_bytes":  524288,
    "used_label":  "512.0 KB",
    "quota_bytes": 2147483648,
    "quota_label": "2.00 GB",
    "quota_pct":   0.02,
    "by_category": {
      "avatars": { "files": 2, "bytes": 400000, "label": "390.6 KB" },
      "kyc":     { "files": 1, "bytes": 124288, "label": "121.4 KB" }
    }
  },
  "api_keys": [
    {
      "id": "uuid", "name": "Clé principale",
      "key_prefix": "shk_abc1…",          // jamais la clé complète
      "revoked": false, "created_at": "...", "last_used": "..."
    }
  ],
  "webhooks": [
    { "id": "uuid", "url": "https://...", "events": "*", "is_active": true }
  ]
}
```

### `GET /v1/admin/files` — Tous les fichiers

**Params :** `?page=1&limit=20&category=avatars&client_id=uuid`

```json
// RESPONSE 200
{
  "items": [
    {
      "file_id":   "uuid",
      "client_id": "uuid",
      "owner":     "user-123",
      "category":  "avatars",
      "mime_type": "image/jpeg",
      "size":      "84.4 KB",
      "size_bytes": 86381,
      "encrypted": false,
      "has_thumb": true,
      "tags":      { "user_id": "123" },
      "version":   1,
      "created_at": "2026-10-15T10:00:00"
    }
  ],
  "total": 8, "page": 1, "limit": 20, "pages": 1
}
```

### `GET /v1/admin/logs` — Audit logs

**Params :** `?limit=50` (max 500)

```json
// RESPONSE 200
[
  {
    "id":        1,
    "file_id":   "uuid",
    "user":      "user-123",
    "role":      "user",
    "action":    "upload",           // upload|download|download_signed|delete
    "ip":        "127.0.0.1",
    "timestamp": "2026-10-15T10:00:00",
    "success":   true
  }
]
```

### `POST /v1/admin/clients/{client_id}/suspend` — Suspendre

```json
{ "id": "uuid", "is_active": false, "message": "Account suspended" }
```

### `POST /v1/admin/clients/{client_id}/activate` — Réactiver

```json
{ "id": "uuid", "is_active": true, "message": "Account activated" }
```

---

## Pages HTML

| Route | Description |
|-------|-------------|
| `GET /` | Landing page |
| `GET /ui` | Landing page |
| `GET /ui/dashboard.html` | Dashboard client (login JWT) |
| `GET /integration` | Dashboard intégrateur |
| `GET /test` | Suite de tests API |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc |

---

## Limites par plan

| Fonctionnalité | Free (0€) | Starter (5€) | Pro (19€) | Business (79€) |
|----------------|-----------|-------------|-----------|----------------|
| Stockage | 500 MB | 2 GB | 50 GB | 500 GB |
| Clés API max | 1 | 2 | 3 | 10 |
| TTL URL signée max | 60s | 120s | 300s | 3600s |
| Chiffrement AES-256 | ❌ | ✅ | ✅ | ✅ |
| Webhooks | ❌ | ✅ | ✅ | ✅ |
| Upload bulk | ❌ | ❌ | ✅ | ✅ |
| Rate limit uploads | 60/min | 60/min | 100/min | 200/min |
| Support | Community | Email | Email 24h | Prioritaire + SLA |

---

*Généré automatiquement — StorageHub v2.0 · WIB Company · octobre 2026*
