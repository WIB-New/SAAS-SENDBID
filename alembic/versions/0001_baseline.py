"""Baseline — schéma complet StorageHub (v2).

Pour une base existante déjà à jour : `alembic stamp 0001`.
Pour une base vide : `alembic upgrade head` crée toutes les tables.

Revision ID: 0001
Revises:
Create Date: 2026-02-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crée toutes les tables du modèle courant si elles sont absentes."""
    from app.database import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind, checkfirst=True)


def downgrade() -> None:
    from app.database import Base
    bind = op.get_bind()
    Base.metadata.drop_all(bind, checkfirst=True)
