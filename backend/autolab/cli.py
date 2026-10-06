"""Admin commands. Run: uv run autolab <command> --help"""

import argparse
import asyncio
import sys

from autolab.db.engine import make_engine, make_session_factory
from autolab.errors import AppError
from autolab.services.admins import grant_admin


async def create_admin(user_id: int) -> None:
    engine = make_engine()
    try:
        async with make_session_factory(engine)() as db:
            await grant_admin(db, user_id, granted_by="cli")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="autolab")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-admin", help="give admin rights to a user")
    create.add_argument("user_id", type=int)

    args = parser.parse_args()
    try:
        if args.command == "create-admin":
            asyncio.run(create_admin(args.user_id))
            print(f"User {args.user_id} is now an admin.")
    except AppError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
