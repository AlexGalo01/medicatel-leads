from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mle.db.base import async_session_factory
from mle.db.models import User
from mle.repositories.users_repository import UsersRepository
from mle.services.jwt_service import decode_access_token

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    token = credentials.credentials
    try:
        uid = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token no válido o expirado.") from exc
    async with async_session_factory() as session:
        repo = UsersRepository(session)
        user = await repo.get_by_id(uid)
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Usuario no válido o inactivo.")
        session.expunge(user)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol administrador.")
    return user


def require_permission(*perms: str):
    """Dependencia que exige que el usuario tenga TODOS los permisos listados. Admin los tiene implícitamente."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role == "admin":
            return user
        user_perms = set(user.permissions) if isinstance(user.permissions, list) else set()
        missing = set(perms) - user_perms
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Permiso(s) requerido(s): {', '.join(sorted(missing))}",
            )
        return user

    return checker
