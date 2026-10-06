"""Admin commands. Run: uv run autolab <command> --help"""

import argparse
import asyncio
import mimetypes
import sys
from pathlib import Path

from autolab.config import get_settings
from autolab.db.engine import make_engine, make_session_factory
from autolab.db.models import Workspace
from autolab.errors import AppError
from autolab.services.admins import grant_admin
from autolab.services.files import chunks_of, store_file


async def create_admin(user_id: int) -> None:
    engine = make_engine()
    try:
        async with make_session_factory(engine)() as db:
            await grant_admin(db, user_id, granted_by="cli")
    finally:
        await engine.dispose()


async def add_file(workspace_id: int, path: Path, move: bool) -> int:
    """Copy a file from the server's disk into a workspace. With --move,
    the original is deleted after the copy is saved."""
    if not path.is_file():
        raise AppError(404, "file_not_found", f"No file at {path}")
    engine = make_engine()
    try:
        async with make_session_factory(engine)() as db:
            if await db.get(Workspace, workspace_id) is None:
                raise AppError(404, "workspace_not_found", f"Workspace {workspace_id} not found")
            stored = await store_file(
                db,
                get_settings(),
                workspace_id=workspace_id,
                chunks=chunks_of(path),
                original_name=path.name,
                original_path=str(path.resolve()),
                content_type=mimetypes.guess_type(path.name)[0],
                actor=None,
            )
    finally:
        await engine.dispose()
    if move:
        path.unlink()
    return stored.id


def main() -> None:
    parser = argparse.ArgumentParser(prog="autolab")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-admin", help="give admin rights to a user")
    create.add_argument("user_id", type=int)

    add = commands.add_parser("add-file", help="copy a file from this server into a workspace")
    add.add_argument("workspace_id", type=int)
    add.add_argument("path", type=Path)
    add.add_argument("--move", action="store_true", help="delete the original after the copy")

    args = parser.parse_args()
    try:
        if args.command == "create-admin":
            asyncio.run(create_admin(args.user_id))
            print(f"User {args.user_id} is now an admin.")
        elif args.command == "add-file":
            file_id = asyncio.run(add_file(args.workspace_id, args.path, args.move))
            print(f"Added as file {file_id} of workspace {args.workspace_id}.")
    except AppError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
