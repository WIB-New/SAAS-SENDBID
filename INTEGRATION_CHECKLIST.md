# StorageHub — Storage Service
# Liste de tests d'intégration

> **Comment lire ce document**
> Chaque test indique : le endpoint testé, les conditions d'entrée, le résultat attendu, et le statut HTTP attendu.
> L'UI de test (`/ui`) exécute automatiquement les cas marqués 🤖.
> Les cas marqués 🖐️ sont à tester manuellement ou via Postman/curl.

---

## BLOC 1 — INFRASTRUCTURE & CONNECTIVITÉ

| # | Test | Méthode | Endpoint | Attendu | Auto |
|---|------|---------|----------|---------|------|
| 1.1 | Liveness probe — service up | GET | `/v1/ping` | `200` `{"pong":true}` | 🤖 |
| 1.2 | Readiness probe — DB + disque OK | GET | `/health` | `200` `{"status":"ok"}` | 🤖 |
| 1.3 | Headers de service présents | GET | `/v1/ping` | Headers `X-Request-ID`, `X-Service-Version`, `X-Response-Time` | 🤖 |
| 1.4 | Request-ID transmis depuis le client | GET | `/v1/ping` + `X-Request-ID: my-id` | `X-Request-ID: my-id` en réponse | 🤖 |
| 1.5 | Info service pour intégration | GET | `/v1/info` | `200` — liste catégories, limites, MIME autorisés | 🤖 |
| 1.6 | Métriques Prometheus | GET | `/v1/metrics` | `200` texte brut avec `storagehub_disk_*` | 🤖 |
| 1.7 | Documentation Swagger accessible | GET | `/docs` | `200` — interface Swagger | 🖐️ |
| 1.8 | Documentation ReDoc accessible | GET | `/redoc` | `200` — interface ReDoc | 🖐️ |

---

## BLOC 2 — AUTHENTIFICATION

| # | Test | Entrée | Attendu | Code erreur |
|---|------|--------|---------|-------------|
| 2.1 | Sans API Key | Aucun header | `401` | `MISSING_API_KEY` |
| 2.2 | API Key invalide | `X-API-Key: wrong-key` | `403` | `INVALID_API_KEY` |
| 2.3 | API Key correcte | `X-API-Key: dev-api-key` | `200/201` | — |
| 2.4 | HMAC valide (production) | API Key + Timestamp + Signature | `200/201` | — |
| 2.5 | HMAC avec timestamp expiré (>30s) | Timestamp ancien | `403` | `INVALID_HMAC` |
| 2.6 | HMAC avec signature falsifiée | Signature altérée | `403` | `INVALID_HMAC` |
| 2.7 | HMAC obligatoire en production | `APP_ENV=production` sans HMAC | `403` | `HMAC_REQUIRED` |
| 2.8 | User-Id transmis correctement | `X-User-Id: user-001` | Fichier assigné à `user-001` | — |
| 2.9 | Role admin transmis | `X-User-Role: admin` | Accès à tous les fichiers | — |

---

## BLOC 3 — UPLOAD DE FICHIER (POST /v1/files)

### 3A — Uploads valides

| # | Test | Fichier | Catégorie | Attendu |
|---|------|---------|-----------|---------|
| 3A.1 | JPEG avatar | JPEG 1×1 px | `avatars` | `201` — `url` présente, `public: true` |
| 3A.2 | PNG avatar | PNG 1×1 px | `avatars` | `201` — `mime: image/png` |
| 3A.3 | WebP avatar | WebP valide | `avatars` | `201` — `mime: image/webp` |
| 3A.4 | JPEG KYC | JPEG valide | `kyc` | `201` — `url: null`, `public: false` |
| 3A.5 | PNG KYC | PNG valide | `kyc` | `201` — `url: null` |
| 3A.6 | PDF KYC | PDF minimal | `kyc` | `201` — `mime: application/pdf` |
| 3A.7 | JPEG reçu | JPEG valide | `receipts` | `201` — `url: null`, `public: false` |
| 3A.8 | PDF reçu | PDF minimal | `receipts` | `201` — `mime: application/pdf` |
| 3A.9 | Réponse contient checksum SHA-256 | N'importe quel fichier | `avatars` | `checksum` = 64 chars hex |
| 3A.10 | File ID est un UUID v4 | N'importe quel fichier | `avatars` | `file_id` = format UUID |
| 3A.11 | Nom de fichier serveur ≠ nom client | `../../malicious.jpg` | `avatars` | `file_id` UUID, pas le nom client |
| 3A.12 | EXIF supprimé des images | JPEG avec métadonnées GPS | `avatars` | Fichier retourné sans EXIF |
| 3A.13 | owner_user_id optionnel | Champ absent | `avatars` | Propriétaire = user du header `X-User-Id` |

### 3B — Uploads invalides (sécurité)

| # | Test | Fichier | Attendu | Code erreur |
|---|------|---------|---------|-------------|
| 3B.1 | Fichier vide | 0 octet | `400` | `EMPTY_FILE` |
| 3B.2 | Exécutable Windows | Header `MZ` (PE) | `400` | `DANGEROUS_FILE` |
| 3B.3 | Exécutable Linux | Header `\x7fELF` | `400` | `DANGEROUS_FILE` |
| 3B.4 | Script shell | Header `#!/bin/bash` | `400` | `DANGEROUS_FILE` |
| 3B.5 | Avatar trop grand | > 5 MB | `413` | `FILE_TOO_LARGE` |
| 3B.6 | KYC trop grand | > 10 MB | `413` | `FILE_TOO_LARGE` |
| 3B.7 | MIME non autorisé pour la catégorie | PDF → avatars | `400` | `INVALID_MIME` |
| 3B.8 | MIME déclaré ≠ contenu réel | Extension `.jpg` mais contenu `.exe` | `400` | `DANGEROUS_FILE` |
| 3B.9 | Catégorie invalide | `category: ../../etc` | `400` | `INVALID_CATEGORY` |
| 3B.10 | Path traversal dans le nom | `../../../etc/passwd.jpg` | `201` avec UUID (nom neutralisé) OU `400` | — |
| 3B.11 | Sans champ `file` | Form vide | `422` | `INVALID_CATEGORY` |
| 3B.12 | Sans champ `category` | Fichier sans catégorie | `422` | validation error |

---

## BLOC 4 — CONTRÔLE D'ACCÈS AUX FICHIERS

### 4A — Accès autorisés

| # | Test | Qui demande | Fichier de qui | Attendu |
|---|------|-------------|----------------|---------|
| 4A.1 | Propriétaire → son propre KYC | `user-001` | `user-001` | `200` — stream |
| 4A.2 | Propriétaire → son propre reçu | `user-001` | `user-001` | `200` — stream |
| 4A.3 | Admin → KYC de n'importe qui | `admin` (role=admin) | `user-001` | `200` — stream |
| 4A.4 | Agent KYC → KYC de n'importe qui | `agent` (role=kyc_agent) | `user-001` | `200` — stream |
| 4A.5 | Propriétaire → métadonnées | `user-001` | `user-001` | `200` — JSON meta |
| 4A.6 | Admin → liste tous les fichiers | `admin` (role=admin) | Tous | `200` — liste complète |

### 4B — Accès refusés

| # | Test | Qui demande | Fichier de qui | Attendu | Code erreur |
|---|------|-------------|----------------|---------|-------------|
| 4B.1 | Autre user → KYC d'un tiers | `user-002` | `user-001` | `403` | `ACCESS_DENIED` |
| 4B.2 | Autre user → reçu d'un tiers | `user-002` | `user-001` | `403` | `ACCESS_DENIED` |
| 4B.3 | Sans auth → fichier sensible | Aucun header | `user-001` | `401` | `MISSING_API_KEY` |
| 4B.4 | User → liste = seulement ses fichiers | `user-001` | Mix users | `200` — seulement user-001 |
| 4B.5 | Autre user → supprimer fichier tiers | `user-002` DELETE | `user-001` | `403` | `ACCESS_DENIED` |
| 4B.6 | File ID inexistant | N'importe qui | ID aléatoire | `404` | `FILE_NOT_FOUND` |
| 4B.7 | File ID supprimé (soft delete) | Propriétaire | Fichier deleted | `404` | `FILE_NOT_FOUND` |

---

## BLOC 5 — SÉCURITÉ CRITIQUE (fichiers sensibles)

> ⚠️ Ces tests sont les plus importants. Un échec = faille de sécurité grave.

| # | Test | Description | Attendu |
|---|------|-------------|---------|
| 5.1 🔴 | KYC jamais accessible publiquement | GET `/v1/public/avatars/{kyc_file_id}` | `403` ou `404` — JAMAIS `200` |
| 5.2 🔴 | Reçu jamais accessible publiquement | GET `/v1/public/avatars/{receipt_file_id}` | `403` ou `404` — JAMAIS `200` |
| 5.3 🔴 | Réponse KYC sans URL publique | Upload KYC → champ `url` | `null` — JAMAIS une URL |
| 5.4 🔴 | Réponse reçu sans URL publique | Upload reçu → champ `url` | `null` — JAMAIS une URL |
| 5.5 🔴 | Listing répertoire désactivé | GET `/uploads/kyc/` | `404` ou `403` |
| 5.6 🔴 | Cache-Control sensible | Télécharger un KYC | Header `Cache-Control: no-store` |
| 5.7 🟡 | X-Content-Type-Options | Toute réponse binaire | Header `X-Content-Type-Options: nosniff` |
| 5.8 🟡 | Content-Security-Policy sur sensibles | Stream KYC | Header `Content-Security-Policy: default-src 'none'` |
| 5.9 🟡 | Pas d'indexation robots | Stream KYC | Header `X-Robots-Tag: noindex, nofollow` |

---

## BLOC 6 — URLS SIGNÉES

| # | Test | Description | Attendu |
|---|------|-------------|---------|
| 6.1 | Génération URL signée | GET `/v1/files/{id}/signed` | `200` — URL + `expires_at` + `ttl_seconds` |
| 6.2 | TTL personnalisé | `?ttl=300` | `ttl_seconds: 300` |
| 6.3 | Download via URL signée valide | GET URL signée (dans TTL) | `200` — binaire streamé |
| 6.4 | URL signée expirée | URL avec `expires` dans le passé | `403` | `SIGNED_URL_EXPIRED` |
| 6.5 | Signature falsifiée | Modifier le paramètre `sig` | `403` | `SIGNED_URL_INVALID` |
| 6.6 | Timestamp modifié | Modifier `expires` sans changer `sig` | `403` | `SIGNED_URL_INVALID` |
| 6.7 | URL signée d'un autre fichier | Utiliser la sig de A pour accéder à B | `403` | `SIGNED_URL_INVALID` |
| 6.8 | URL signée sans auth header | GET URL signée sans `X-API-Key` | `200` (auth header non requis) | — |

---

## BLOC 7 — SUPPRESSION

| # | Test | Description | Attendu |
|---|------|-------------|---------|
| 7.1 | Suppression logique | DELETE par le propriétaire | `200` `{"deleted":true}` |
| 7.2 | Fichier inaccessible après suppression | GET après DELETE | `404` |
| 7.3 | Suppression par admin | DELETE par admin d'un fichier tiers | `200` |
| 7.4 | Double suppression | DELETE → DELETE sur même fichier | `404` au 2ème appel |
| 7.5 | Suppression par non-propriétaire | DELETE par user-002 sur user-001 | `403` |

---

## BLOC 8 — RÉPONSES & CONTRAT D'API

| # | Test | Description | Attendu |
|---|------|-------------|---------|
| 8.1 | Header `X-Request-ID` sur chaque réponse | Toute requête | Header présent, format UUID |
| 8.2 | Header `X-Service-Version` | Toute requête | `X-Service-Version: 1.0.0` |
| 8.3 | Header `X-Response-Time` | Toute requête | Ex: `X-Response-Time: 12.5ms` |
| 8.4 | Propagation `X-Request-ID` client | Envoyer `X-Request-ID: my-trace-id` | Retourné identique en réponse |
| 8.5 | Erreurs au format standard | Toute erreur | `{"success":false,"code":"...","error":"...","request_id":"..."}` |
| 8.6 | Succès au format standard | Upload | `{"success":true,"..."}` + champs métier |
| 8.7 | Content-Type `application/json` | Toute réponse JSON | Header `Content-Type: application/json` |
| 8.8 | Dates en ISO 8601 UTC | `created_at`, `expires_at` | Format `2026-10-08T10:30:00` |
| 8.9 | Checksum SHA-256 valide | Upload → champ `checksum` | 64 caractères hexadécimaux |
| 8.10 | CORS headers présents | Requête cross-origin | `Access-Control-Allow-Origin: *` en dev |

---

## BLOC 9 — HEALTH & MONITORING

| # | Test | Description | Attendu |
|---|------|-------------|---------|
| 9.1 | Health en mode DB down | Couper PostgreSQL | `200` `{"status":"degraded"}` |
| 9.2 | Health avec disque > 80% | Remplir le disque | `200` `{"status":"degraded","checks":{"disk":{"status":"alert"}}}` |
| 9.3 | Health indique les dossiers présents | GET `/health` | `checks.dir_avatars: ok`, `dir_kyc: ok`, `dir_receipts: ok` |
| 9.4 | Uptime croissant | 2 appels successifs à `/health` | `uptime_seconds` croissant |
| 9.5 | Métriques format Prometheus valide | GET `/v1/metrics` | Chaque ligne `# HELP`, `# TYPE`, valeur numérique |
| 9.6 | `/v1/info` retourne les limites | GET `/v1/info` | `categories.kyc.max_size_mb: 10`, MIME list |

---

## BLOC 10 — INTÉGRATION DJANGO (Client HTTP)

| # | Test | Description | Attendu |
|---|------|-------------|---------|
| 10.1 | `client.upload_avatar(file, user_id)` | Appel depuis Django | Retourne `{"file_id","url","checksum"}` |
| 10.2 | `client.upload_kyc(file, user_id)` | Appel depuis Django | Retourne `{"file_id","checksum"}` sans URL |
| 10.3 | `client.get_file_url(file_id, user_id)` | URL signée KYC | URL valide, non-expirée |
| 10.4 | `client.delete_file(file_id, user_id)` | Suppression | `True` retourné |
| 10.5 | HMAC calculé correctement | Vérifier la signature côté storage | `200` — pas de `403 INVALID_HMAC` |
| 10.6 | `StorageError` levée si 4xx/5xx | Passer une mauvaise catégorie | Exception `StorageError` levée |
| 10.7 | Timeout réseau | Simuler une latence > 30s | `requests.Timeout` propagé |

---

## BLOC 11 — PERFORMANCE & LIMITES

| # | Test | Description | Attendu |
|---|------|-------------|---------|
| 11.1 | Upload fichier max (5 MB avatar) | Fichier exactement 5 MB | `201` |
| 11.2 | Upload fichier max (10 MB KYC) | Fichier exactement 10 MB | `201` |
| 11.3 | Upload fichier max+1 Ko | 5 MB + 1 Ko pour avatar | `413` |
| 11.4 | Temps de réponse upload < 3s | Fichier 5 MB | `X-Response-Time` < 3000ms |
| 11.5 | Temps de réponse download < 1s | Fichier 1 MB | `X-Response-Time` < 1000ms |
| 11.6 | 10 uploads simultanés | 10 requêtes en parallèle | Tous `201`, pas de race condition |
| 11.7 | Pagination liste (100 max) | > 100 fichiers en base | Retourne exactement 100 résultats |

---

## RÉSUMÉ EXÉCUTIF

| Bloc | Tests | Priorité | Automatisable |
|------|-------|----------|---------------|
| 1 — Infrastructure | 8 | 🔴 Critique | 100% |
| 2 — Authentification | 9 | 🔴 Critique | 80% |
| 3 — Upload | 25 | 🔴 Critique | 100% |
| 4 — Contrôle d'accès | 13 | 🔴 Critique | 100% |
| 5 — Sécurité sensible | 9 | 🔴 Critique | 90% |
| 6 — URLs signées | 8 | 🟠 Important | 100% |
| 7 — Suppression | 5 | 🟠 Important | 100% |
| 8 — Contrat API | 10 | 🟠 Important | 100% |
| 9 — Monitoring | 6 | 🟡 Modéré | 60% |
| 10 — Intégration Django | 7 | 🟠 Important | 70% |
| 11 — Performance | 7 | 🟡 Modéré | 80% |
| **TOTAL** | **107** | | **~90%** |

---

## COMMANDES CURL DE RÉFÉRENCE

```bash
BASE="http://localhost:8080"
KEY="dev-api-key"
UID="user-001"

# 1. Ping
curl -s $BASE/v1/ping | jq .

# 2. Health
curl -s $BASE/health | jq .

# 3. Upload avatar
curl -s -X POST $BASE/v1/files \
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" -H "X-User-Role: user" \
  -F "file=@avatar.jpg" -F "category=avatars" | jq .

# 4. Upload KYC
curl -s -X POST $BASE/v1/files \
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" -H "X-User-Role: user" \
  -F "file=@cni.pdf" -F "category=kyc" | jq .

# 5. Liste des fichiers
curl -s "$BASE/v1/files" \
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" | jq .

# 6. Métadonnées
curl -s "$BASE/v1/files/{FILE_ID}/meta" \
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" | jq .

# 7. URL signée
curl -s "$BASE/v1/files/{FILE_ID}/signed?ttl=60" \
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" | jq .

# 8. Test sécurité — KYC via URL publique (doit retourner 403/404)
curl -s -o /dev/null -w "%{http_code}" "$BASE/v1/public/avatars/{KYC_FILE_ID}"

# 9. Suppression
curl -s -X DELETE "$BASE/v1/files/{FILE_ID}" \
  -H "X-API-Key: $KEY" -H "X-User-Id: $UID" | jq .

# 10. Headers de service
curl -si "$BASE/v1/ping" | grep -E "X-Request-ID|X-Service-Version|X-Response-Time"
```
