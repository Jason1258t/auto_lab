"""User files of a workspace (decided 2026-10-07, migration 0003).

A file is copied into the workspace folder
data/workspaces/<workspace_id>/files/<file_name>. The row keeps where it
came from (original name and path) and its current name on disk.
"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from autolab.db.models.base import Base, bigint_pk, created_at


class WorkspaceFile(Base):
    __tablename__ = "workspace_files"

    id: Mapped[int] = bigint_pk()
    # CASCADE: the files belong to the workspace.
    workspace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    original_name: Mapped[str] = mapped_column(Text)  # "Chapter 1.pdf"
    # Path the user gave, for people only ("notes/course/Chapter 1.pdf").
    # Never used to open a file.
    original_path: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)  # current name on disk: "42_Chapter_1.pdf"
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        # Also serves as the index for "files of a workspace".
        UniqueConstraint("workspace_id", "file_name"),
        CheckConstraint("size_bytes >= 0", name="workspace_files_size_bytes_check"),
    )
