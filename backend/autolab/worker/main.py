"""The worker process. Run: uv run autolab-worker

Start:
1. LLM calls left queued/running -> failed ("manager restarted").
2. Tasks left running -> queued again; their running step -> pending.
   (One worker for now. Several workers would need a heartbeat first.)
3. Sync pipelines/ -> pipeline_versions. Any problem stops the worker.
Then: take queued tasks one by one, and clean up deleted LLM logs.
"""

import asyncio
import logging
import signal
from pathlib import Path

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings, get_settings
from autolab.db.engine import make_engine, make_session_factory
from autolab.db.models import LogDeletion, Task, TaskStep
from autolab.db.models.enums import TaskStatus, TaskStepStatus
from autolab.logstore import LogStore, make_log_store
from autolab.worker.gateway import Adapter, make_adapters
from autolab.worker.llm_manager import LlmManager, SessionFactory
from autolab.worker.pipelines import PipelineError, sync_pipelines
from autolab.worker.runner import TaskRunner, now
from autolab.worker.web import Resolver, resolve

log = logging.getLogger("autolab.worker")


async def claim_next_task(db: AsyncSession) -> int | None:
    """Take the oldest queued task, in one transaction.

    FOR UPDATE SKIP LOCKED: a row another worker has locked is skipped,
    so two workers never take the same task. Uses the partial index
    tasks_active_status_idx.
    """
    task_id = await db.scalar(
        select(Task.id)
        .where(Task.status == TaskStatus.QUEUED)
        .order_by(Task.created_at, Task.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task_id is not None:
        await db.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(status=TaskStatus.RUNNING, started_at=now())
        )
    await db.commit()
    return task_id


async def recover_tasks(db: AsyncSession) -> int:
    """Tasks the last worker left running go back to the queue."""
    running = select(Task.id).where(Task.status == TaskStatus.RUNNING)
    await db.execute(
        update(TaskStep)
        .where(TaskStep.task_id.in_(running), TaskStep.status == TaskStepStatus.RUNNING)
        .values(status=TaskStepStatus.PENDING)
    )
    result = await db.execute(
        update(Task).where(Task.status == TaskStatus.RUNNING).values(status=TaskStatus.QUEUED)
    )
    await db.commit()
    return result.rowcount


async def clean_up_logs(db: AsyncSession, log_store: LogStore, batch: int = 500) -> int:
    """Delete logs of deleted LLM calls (the log_deletions outbox, filled
    by a DB trigger). A row is removed only after its log is gone."""
    call_ids = list(await db.scalars(select(LogDeletion.call_id).limit(batch)))
    for call_id in call_ids:
        await log_store.delete(call_id)
    if call_ids:
        await db.execute(delete(LogDeletion).where(LogDeletion.call_id.in_(call_ids)))
        await db.commit()
    return len(call_ids)


class Worker:
    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings,
        log_store: LogStore,
        adapters: dict[str, Adapter],
        http: httpx.AsyncClient | None = None,
        resolver: Resolver = resolve,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.log_store = log_store
        self.llm = LlmManager(session_factory, log_store, adapters)
        # One HTTP client for search and page downloads.
        self.http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0), headers={"User-Agent": settings.fetch_user_agent}
        )
        self.runner = TaskRunner(session_factory, self.llm, settings, self.http, resolver)

    async def start(self) -> None:
        failed_calls = await self.llm.recover()
        async with self.session_factory() as db:
            requeued = await recover_tasks(db)
        async with self.session_factory() as db:
            added = await sync_pipelines(db, Path(self.settings.pipelines_dir))
        log.info(
            "worker started: %s calls marked failed, %s tasks queued again, new versions: %s",
            failed_calls,
            requeued,
            ", ".join(added) or "none",
        )

    async def run_once(self) -> bool:
        """Take and run one task. False if the queue was empty."""
        async with self.session_factory() as db:
            task_id = await claim_next_task(db)
        if task_id is None:
            return False
        log.info("task %s: started", task_id)
        status = await self.runner.run(task_id)
        log.info("task %s: %s", task_id, status)
        return True

    async def run_forever(self) -> None:
        cleanup = asyncio.create_task(self._cleanup_forever())
        try:
            while True:
                if not await self.run_once():
                    await asyncio.sleep(self.settings.worker_poll_seconds)
        finally:
            cleanup.cancel()
            await self.llm.close()
            await self.http.aclose()

    async def _cleanup_forever(self) -> None:
        while True:
            try:
                async with self.session_factory() as db:
                    removed = await clean_up_logs(db, self.log_store)
                if removed:
                    log.info("removed %s deleted LLM logs", removed)
            except Exception:
                log.exception("log cleanup failed")
            await asyncio.sleep(self.settings.log_cleanup_seconds)


async def _main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    worker = Worker(
        make_session_factory(engine),
        settings,
        make_log_store(settings),
        make_adapters(settings.llm_timeout_seconds),
    )
    # SIGTERM (systemd, docker stop) and Ctrl+C: stop cleanly. A task that
    # is running is queued again at the next start (recover_tasks).
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await worker.start()
        run = asyncio.create_task(worker.run_forever())
        await stop.wait()
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
        log.info("worker stopped")
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(_main())
    except PipelineError as exc:
        log.error("%s", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
