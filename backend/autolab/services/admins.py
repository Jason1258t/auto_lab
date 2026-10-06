"""Admin rights. A row in `admins` = an admin."""

from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Admin, User
from autolab.errors import AppError
from autolab.services import activity


async def is_admin(db: AsyncSession, user_id: int) -> bool:
    return await db.get(Admin, user_id) is not None


async def grant_admin(
    db: AsyncSession, user_id: int, *, granted_by: str, actor: User | None = None
) -> Admin:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(404, "user_not_found", f"User {user_id} not found")
    if await is_admin(db, user_id):
        raise AppError(409, "already_admin", f"User {user_id} is already an admin")

    admin = Admin(user_id=user_id, granted_by=granted_by)
    db.add(admin)
    activity.record(
        db,
        "admin_granted",
        actor=actor,
        target_type="user",
        target_id=user.id,
        target_label=user.username,
        details={"granted_by": granted_by},
    )
    await db.commit()
    return admin


async def revoke_admin(db: AsyncSession, user_id: int, *, actor: User) -> None:
    """An admin cannot remove themselves, so the last admin cannot lock
    everyone out by mistake."""
    if user_id == actor.id:
        raise AppError(409, "cannot_revoke_self", "You cannot remove your own admin rights")
    admin = await db.get(Admin, user_id)
    if admin is None:
        raise AppError(404, "admin_not_found", f"User {user_id} is not an admin")
    user = await db.get(User, user_id)
    await db.delete(admin)
    activity.record(
        db,
        "admin_revoked",
        actor=actor,
        target_type="user",
        target_id=user_id,
        target_label=user.username if user else None,
    )
    await db.commit()
