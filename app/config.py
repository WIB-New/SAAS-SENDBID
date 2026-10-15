"""
StorageHub — Storage Service Configuration
"""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Serveur
    app_env:  str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    base_url: str = "http://localhost:8080"

    # Base de données
    database_url: str = "sqlite+aiosqlite:///./sendbid_storage.db"

    # Auth
    api_key:                        str = "dev-api-key-sendbid-2024"
    hmac_secret:                    str = "dev-hmac-secret-sendbid-2024"
    hmac_timestamp_tolerance_seconds: int = 30

    # Chiffrement au repos (KYC + reçus)
    encryption_key: str = "dev-encryption-key-sendbid-2024"

    # Stockage
    upload_root:          str = "./uploads"
    max_size_avatar_mb:   int = 5
    max_size_kyc_mb:      int = 10
    max_size_receipt_mb:  int = 10
    storage_backend:      str = "local"   # "local" | "s3"

    # S3 / Cloudflare R2 / MinIO (si storage_backend = "s3")
    s3_bucket:          str = "storagehub"
    s3_endpoint_url:    str = ""
    s3_access_key:      str = ""
    s3_secret_key:      str = ""
    s3_region:          str = "us-east-1"
    s3_public_base_url: str = ""

    # URLs signées
    signed_url_ttl: int = 60

    # CDN
    cdn_base_url: str = "http://localhost:8080"

    # Monitoring
    disk_alert_threshold_percent: int = 80

    # Sécurité optionnelle
    virustotal_api_key: str = ""   # Laissez vide pour désactiver

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_root)

    @property
    def max_sizes_bytes(self) -> dict:
        return {
            "avatars":  self.max_size_avatar_mb  * 1024 * 1024,
            "kyc":      self.max_size_kyc_mb     * 1024 * 1024,
            "receipts": self.max_size_receipt_mb * 1024 * 1024,
        }

    @property
    def allowed_mimes(self) -> dict:
        return {
            "avatars":  ["image/jpeg", "image/png", "image/webp"],
            "kyc":      ["image/jpeg", "image/png", "application/pdf"],
            "receipts": ["image/jpeg", "image/png", "application/pdf"],
        }

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


# ── Plans d'abonnement ─────────────────────────────────────────────────────────
# Chaque plan définit un niveau de service qui s'applique à une application externe.
# Les limites sont appliquées côté serveur à chaque upload.
PLANS = {
    "free": {
        "name":               "Gratuit",
        "price_monthly":      0,
        "storage_mb":         500,           # 500 MB
        "max_keys":           1,
        "signed_url_max_ttl": 60,            # 1 minute
        "support":            "Community",
        "upload_rate_per_min": 20,
        "max_file_size_mb":   5,
        "webhooks":           False,
        "encryption":         False,         # pas de chiffrement sur le plan gratuit
        "bulk_upload":        False,
        "badge":              "Starter",
        "color":              "#6b7280",
    },
    "starter": {
        "name":               "Starter",
        "price_monthly":      5,
        "storage_mb":         2 * 1024,      # 2 GB
        "max_keys":           2,
        "signed_url_max_ttl": 120,           # 2 minutes
        "support":            "Email",
        "upload_rate_per_min": 40,
        "max_file_size_mb":   10,
        "webhooks":           True,
        "encryption":         True,
        "bulk_upload":        False,
        "badge":              "Populaire",
        "color":              "#3b82f6",
    },
    "pro": {
        "name":               "Pro",
        "price_monthly":      19,
        "storage_mb":         50 * 1024,     # 50 GB
        "max_keys":           5,
        "signed_url_max_ttl": 300,           # 5 minutes
        "support":            "Email 24h",
        "upload_rate_per_min": 60,
        "max_file_size_mb":   25,
        "webhooks":           True,
        "encryption":         True,
        "bulk_upload":        True,
        "badge":              "Pro",
        "color":              "#8b5cf6",
    },
    "business": {
        "name":               "Business",
        "price_monthly":      79,
        "storage_mb":         500 * 1024,    # 500 GB
        "max_keys":           20,
        "signed_url_max_ttl": 3600,          # 1 heure
        "support":            "Prioritaire + SLA 99.9%",
        "upload_rate_per_min": 300,
        "max_file_size_mb":   100,
        "webhooks":           True,
        "encryption":         True,
        "bulk_upload":        True,
        "badge":              "Entreprise",
        "color":              "#f59e0b",
    },
}


def get_plan(plan_id: str) -> dict:
    return PLANS.get(plan_id, PLANS["free"])


settings = Settings()
