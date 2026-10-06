"""The logged-in user's own profile."""

from fastapi import APIRouter

from autolab.api.deps import CurrentPrincipal, DbSession
from autolab.api.schemas.auth import MeOut, MeUpdate, UserOut
from autolab.services.admins import is_admin

router = APIRouter(prefix="/me", tags=["me"])


async def me_out(db: DbSession, principal: CurrentPrincipal) -> MeOut:
    user = UserOut.model_validate(principal.user)
    return MeOut(**user.model_dump(), is_admin=await is_admin(db, principal.user.id))


@router.get("")
async def get_me(principal: CurrentPrincipal, db: DbSession) -> MeOut:
    return await me_out(db, principal)


@router.patch("")
async def update_me(body: MeUpdate, principal: CurrentPrincipal, db: DbSession) -> MeOut:
    principal.user.display_name = body.display_name
    await db.commit()
    return await me_out(db, principal)
