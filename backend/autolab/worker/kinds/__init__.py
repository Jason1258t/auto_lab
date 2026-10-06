"""Step kind handlers. A kind that is valid in a pipeline file but has no
handler here yet fails the task with a clear message.

The research kinds (search, fetch, summarize, verify, synthesize, write)
come in the next step of the build order.
"""

from autolab.worker.kinds.base import Handler, StepContext, StepFailed


async def plan(ctx: StepContext) -> dict:
    """One model call; its answer is the step output."""
    data = await ctx.ask()
    if data is None:
        raise StepFailed("the model gave no valid answer")
    return data


HANDLERS: dict[str, Handler] = {
    "plan": plan,
}

__all__ = ["HANDLERS", "Handler", "StepContext", "StepFailed"]
