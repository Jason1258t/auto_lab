"""Step kind handlers. A kind that is valid in a pipeline file but has no
handler here fails the task with a clear message."""

from autolab.worker.kinds import deep, research
from autolab.worker.kinds.base import Handler, StepContext, StepFailed


async def plan(ctx: StepContext) -> dict:
    """One model call; its answer is the step output."""
    data = await ctx.ask()
    if data is None:
        raise StepFailed("the model gave no valid answer")
    return data


HANDLERS: dict[str, Handler] = {
    "plan": plan,
    **research.HANDLERS,
    **deep.HANDLERS,
}

__all__ = ["HANDLERS", "Handler", "StepContext", "StepFailed"]
