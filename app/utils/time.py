"""Horloge UTC partagée.

Les colonnes du modèle sont `DateTime` naïves (SQLite/Postgres compatibles) —
on centralise ici le moment « maintenant » en UTC naïf pour éviter
`datetime.utcnow()` (déprécié) tout en conservant des timestamps naïfs.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Retourne l'heure UTC courante, naïve (sans tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
