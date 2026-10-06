"""Base class and shared column types for all ORM models.

The models must match the database exactly (names, types, constraints),
so that Alembic finds no difference between them.
"""

import enum

from sqlalchemy import BigInteger, DateTime, Enum, Identity, MetaData, SmallInteger, func
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Same names that PostgreSQL gives by default, e.g. `users_pkey`,
# `users_username_key`, `tasks_workspace_id_fkey`.
NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
    "ix": "%(table_name)s_%(column_0_N_name)s_idx",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def bigint_pk():
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def smallint_pk():
    return mapped_column(SmallInteger, Identity(always=True), primary_key=True)


def created_at():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def pg_enum(enum_class: type[enum.Enum], name: str) -> Enum:
    # Store the values ('queued'), not the Python names (QUEUED).
    return Enum(
        enum_class,
        name=name,
        values_callable=lambda e: [member.value for member in e],
    )
