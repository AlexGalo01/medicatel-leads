from __future__ import annotations

from sqlalchemy import func, select

from mle.core.config import get_settings
from mle.db.base import async_session_factory
from mle.db.models import User
from mle.services.passwords import hash_password


async def ensure_initial_admin() -> None:
    """Crea un admin inicial solo si MLE_INITIAL_ADMIN_* está definido y no hay ningún admin."""
    settings = get_settings()
    email = (settings.mle_initial_admin_email or "").strip().lower()
    password = settings.mle_initial_admin_password
    if not email or not password:
        return
    async with async_session_factory() as session:
        r = await session.execute(select(func.count()).select_from(User).where(User.role == "admin"))
        if (r.scalar_one() or 0) > 0:
            return
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            return
        u = User(
            email=email,
            password_hash=hash_password(password),
            display_name=settings.mle_initial_admin_display_name.strip() or "Administrador",
            role="admin",
            is_active=True,
        )
        session.add(u)
        await session.commit()
