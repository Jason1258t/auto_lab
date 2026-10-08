"""Step kind handlers. A kind that is valid in a pipeline file but has no
handler here fails the task with a clear message."""

from autolab_engine.kinds import code, deep, research
from autolab_engine.kinds.base import Handler, StepContext, StepFailed


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
    **code.HANDLERS,
}

__all__ = ["HANDLERS", "Handler", "StepContext", "StepFailed"]
