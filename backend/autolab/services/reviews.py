"""Reviews of a finished task (results_and_evidence.md).

accepted -> the task is done; its step files are deleted.
rejected -> a comment is required; the task goes back to the queue and
the worker runs the revise steps with that comment (pipeline_spec.md, 7).
"""

import asyncio
import shutil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import TaskReview
from autolab.db.models.enums import ReviewResult, TaskStatus
from autolab.errors import AppError
from autolab.services.permissions import WorkspaceAccess, can_review, forbidden, require_inside
from autolab.services.tasks import TaskView
from autolab.worker.runner import task_dir


async def list_reviews(
    db: AsyncSession, view: TaskView, access: WorkspaceAccess
) -> list[TaskReview]:
    require_inside(access)
    query = select(TaskReview).where(TaskReview.task_id == view.task.id).order_by(TaskReview.id)
    return list(await db.scalars(query))


async def add_review(
    db: AsyncSession,
    settings: Settings,
    view: TaskView,
    access: WorkspaceAccess,
    result: ReviewResult,
    comment: str | None,
) -> TaskReview:
    task = view.task
    if not can_review(access, task.reviewer_id):
        raise forbidden("Only the reviewer, the owner, editors and reviewers can review")
    if task.status != TaskStatus.IN_REVIEW:
        raise AppError(409, "task_not_in_review", f"A {task.status} task cannot be reviewed")
    if result == ReviewResult.REJECTED and not comment:
        raise AppError(
            422, "comment_required", "A rejection needs a comment: it tells the model what to fix"
        )

    review = TaskReview(task_id=task.id, reviewer_id=access.user.id, result=result, comment=comment)
    db.add(review)
    if result == ReviewResult.ACCEPTED:
        # done <=> an accepted review (schema_design.md, "Normalization").
        task.status = TaskStatus.DONE
        task.finished_at = func.now()
    else:
        task.status = TaskStatus.QUEUED
        task.finished_at = None
    await db.commit()
    if result == ReviewResult.ACCEPTED:
        # The step outputs (and the fetched page text) are not kept.
        await asyncio.to_thread(shutil.rmtree, task_dir(settings, task.id), ignore_errors=True)
    return review
