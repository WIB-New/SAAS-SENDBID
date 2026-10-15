"""
StorageHub — Tâche planifiée : purge physique des fichiers supprimés
Les fichiers marqués is_deleted=True depuis plus de PURGE_AFTER_DAYS jours sont
supprimés physiquement du disque et retirés de la base de données.

Planning : quotidiennement à 03:00 UTC via APScheduler.
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("storagehub.purge")

PURGE_AFTER_DAYS = 30


async def purge_deleted_files() -> dict:
    """
    Supprime physiquement les fichiers soft-deleted depuis plus de PURGE_AFTER_DAYS jours.
    Retourne un résumé {purged, errors, skipped}.
    """
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import StoredFile
    from app.utils.backends import get_storage_backend

    threshold = datetime.utcnow() - timedelta(days=PURGE_AFTER_DAYS)
    storage = get_storage_backend()
    purged, errors, skipped = 0, 0, 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StoredFile).where(
                StoredFile.is_deleted == True,
                StoredFile.deleted_at.isnot(None),
                StoredFile.deleted_at < threshold,
            )
        )
        files = result.scalars().all()

        for f in files:
            try:
                ok = storage.delete(f.stored_path)
                if f.thumbnail_path:
                    storage.delete(f.thumbnail_path)
                if ok:
                    await session.delete(f)
                    purged += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.error(f"[PURGE] Error purging file {f.id}: {exc}")
                errors += 1

        await session.commit()

    summary = {"purged": purged, "errors": errors, "skipped": skipped}
    logger.info(f"[PURGE] Daily purge complete — {summary}")
    return summary


def start_scheduler() -> AsyncIOScheduler:
    """Démarre le planificateur de tâches en arrière-plan."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        purge_deleted_files,
        trigger="cron",
        hour=3,
        minute=0,
        id="daily_purge",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("[SCHEDULER] Started — daily purge scheduled at 03:00 UTC")
    return scheduler
