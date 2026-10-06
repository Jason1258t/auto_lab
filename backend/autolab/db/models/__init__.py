"""All ORM models. Import from here, so that every table is registered
on `Base.metadata` (Alembic needs the full list)."""

from autolab.db.models.audit import ActivityEvent
from autolab.db.models.auth import (
    Admin,
    AuthProvider,
    AuthSession,
    PasswordCredential,
    UserIdentity,
)
from autolab.db.models.base import Base
from autolab.db.models.catalog import Capability, Model, ModelCapability, ModelProvider
from autolab.db.models.files import WorkspaceFile
from autolab.db.models.people import Membership, Role, User, Workspace
from autolab.db.models.results import Publication, Publisher, Quote, TaskReview, Work, WorkSource
from autolab.db.models.tasks import (
    LlmCall,
    LlmResponse,
    LogDeletion,
    Pipeline,
    PipelineVersion,
    Task,
    TaskStep,
)

__all__ = [
    "ActivityEvent",
    "Admin",
    "AuthProvider",
    "AuthSession",
    "Base",
    "Capability",
    "LlmCall",
    "LlmResponse",
    "LogDeletion",
    "Membership",
    "Model",
    "ModelCapability",
    "ModelProvider",
    "PasswordCredential",
    "Pipeline",
    "PipelineVersion",
    "Publication",
    "Publisher",
    "Quote",
    "Role",
    "Task",
    "TaskReview",
    "TaskStep",
    "User",
    "UserIdentity",
    "Work",
    "WorkSource",
    "Workspace",
    "WorkspaceFile",
]
