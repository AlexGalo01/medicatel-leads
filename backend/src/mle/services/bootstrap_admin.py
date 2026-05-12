from __future__ import annotations

from sqlalchemy import func, select

from mle.core.config import get_settings
from mle.db.base import async_session_factory
from mle.db.models import User
from mle.services.passwords import hash_password

# Seeder fijo — siempre garantizado en cualquier base de datos
_SEED_EMAIL = "admin@admin.com"
_SEED_PASSWORD = "Asd.1234*"
_SEED_NAME = "Admin"


async def ensure_initial_admin() -> None:
    """
    1. Upsert del admin seeder fijo (admin@admin.com) — siempre activo y con rol admin.
    2. Si hay credenciales MLE_INITIAL_ADMIN_* en .env y no existe ningún otro admin, lo crea también.
    """
    async with async_session_factory() as session:
        # --- Seeder fijo ---
        existing = (await session.execute(select(User).where(User.email == _SEED_EMAIL))).scalar_one_or_none()
        if existing is None:
            session.add(User(
                email=_SEED_EMAIL,
                password_hash=hash_password(_SEED_PASSWORD),
                display_name=_SEED_NAME,
                role="admin",
                is_active=True,
                permissions=["use_search", "manage_opportunities"],
            ))
        else:
            existing.role = "admin"
            existing.is_active = True
            existing.password_hash = hash_password(_SEED_PASSWORD)
        await session.commit()

        # --- Admin desde .env (opcional) ---
        settings = get_settings()
        email = (settings.mle_initial_admin_email or "").strip().lower()
        password = settings.mle_initial_admin_password
        if not email or not password or email == _SEED_EMAIL:
            return
        r = await session.execute(select(func.count()).select_from(User).where(User.role == "admin"))
        if (r.scalar_one() or 0) > 1:
            return
        env_existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if env_existing is not None:
            return
        session.add(User(
            email=email,
            password_hash=hash_password(password),
            display_name=(settings.mle_initial_admin_display_name or "").strip() or "Administrador",
            role="admin",
            is_active=True,
        ))
        await session.commit()
