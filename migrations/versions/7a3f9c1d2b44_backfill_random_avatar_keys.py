"""backfill random avatar keys for existing profiles

Revision ID: 7a3f9c1d2b44
Revises: 29e2955419aa
Create Date: 2026-08-19 09:00:00.000000

"""
import random

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '7a3f9c1d2b44'
down_revision = '29e2955419aa'
branch_labels = None
depends_on = None

# Same set the app's avatar picker (app/users/forms.py's AVATAR_CHOICES)
# and the avatar_icon macro (app/templates/_macros.html) recognize.
# Duplicated here (small, static, unlikely to drift) rather than
# imported, since migrations must stay runnable independent of whatever
# the current app code looks like.
VALID_AVATAR_KEYS = [
    "fa-user-shield", "fa-hat-wizard", "fa-dragon", "fa-khanda",
    "fa-shield-halved", "fa-cat", "fa-dove", "fa-ghost",
    "fa-chess-knight", "fa-spider", "fa-skull", "fa-paw",
]


def upgrade():
    # Every profile created before this fix stored the model's old
    # placeholder default ("characters/idle", not a FontAwesome key the
    # avatar_icon macro recognizes) or NULL, so they all silently fell
    # back to the exact same "fa-user-shield" icon everywhere (chat,
    # rankings, public profiles). Give each one its own random pick
    # instead of leaving old accounts stuck looking identical forever.
    bind = op.get_bind()
    profiles = sa.table(
        "profiles",
        sa.column("id", sa.Integer),
        sa.column("avatar_key", sa.String),
    )
    rows = bind.execute(
        sa.select(profiles.c.id).where(
            sa.or_(profiles.c.avatar_key.is_(None), profiles.c.avatar_key.notin_(VALID_AVATAR_KEYS))
        )
    ).fetchall()

    random.seed(42)  # deterministic across repeated upgrade runs (e.g. in tests)
    for (profile_id,) in rows:
        bind.execute(
            profiles.update()
            .where(profiles.c.id == profile_id)
            .values(avatar_key=random.choice(VALID_AVATAR_KEYS))
        )


def downgrade():
    # Not reversible in any meaningful sense — the old value wasn't a
    # real avatar choice to begin with, so there's nothing to restore to.
    pass
