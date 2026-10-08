"""Token budgets of a model call (drafts/token_budgets.md).

The step's max_tokens is the answer size. Code adds room for thinking
(thinking size classes), keeps the limit under the model's own cap and
the window, and learns the model's speed to set a timeout per call.
"""

import math
from dataclasses import dataclass
from typing import Any, Protocol

from autolab_engine.enums import ModelSizeClass
from autolab_engine.gateway import GenerateResult, Message
from autolab_engine.llm import PromptTooLong

# Window guard (drafts/token_budgets.md, phase 1). We do not have the
# model's tokenizer, so the prompt size is an estimate; 3.5 characters per
# token is a careful guess for English and code (Russian is denser).
CHARS_PER_TOKEN = 3.5
TOKENS_PER_MESSAGE = 10  # the chat template around each message
MIN_ANSWER_TOKENS = 64  # less room than this: do not even try
DEFAULT_REASONING_TOKENS = 1024  # models.reasoning_tokens is NULL

# Per-call timeout (phase 1, item 3): expected time x 2, plus time to load
# the model into memory (a 12 GB model takes about a minute from disk).
TIMEOUT_FACTOR = 2.0
LOAD_SECONDS = 120.0
SPEED_WEIGHT = 0.3  # how much one new call changes the learned speed


class ModelBudget(Protocol):
    """The model fields a budget needs (ModelInfo, or AutoLab's models row)."""

    size_class: ModelSizeClass
    reasoning_tokens: int | None
    max_output_tokens: int | None


@dataclass
class Speed:
    """A model's measured speed in tokens per second, learned from the
    calls of this worker process (none yet after a start)."""

    prompt: float | None = None
    output: float | None = None

    def learn(self, result: GenerateResult) -> None:
        if result.input_tokens and result.prompt_seconds:
            self.prompt = average(self.prompt, result.input_tokens / result.prompt_seconds)
        if result.output_tokens and result.output_seconds:
            self.output = average(self.output, result.output_tokens / result.output_seconds)

    def timeout(self, prompt_tokens: int, max_tokens: int | None) -> float | None:
        """None while the speed is unknown: the adapter's own timeout."""
        if self.prompt is None or self.output is None or max_tokens is None:
            return None
        expected = prompt_tokens / self.prompt + max_tokens / self.output
        return TIMEOUT_FACTOR * expected + LOAD_SECONDS


def average(old: float | None, new: float) -> float:
    return new if old is None else (1 - SPEED_WEIGHT) * old + SPEED_WEIGHT * new


def estimate_tokens(messages: list[Message]) -> int:
    """A rough prompt size in tokens, from the length of the text."""
    chars = sum(len(m.content) for m in messages)
    return math.ceil(chars / CHARS_PER_TOKEN) + TOKENS_PER_MESSAGE * len(messages)


def add_model_budget(params: dict[str, Any], model: ModelBudget) -> dict[str, Any]:
    """max_tokens in a pipeline file is the answer size. A thinking model
    (a *_think class) gets extra room to think before the answer; the
    model's own output cap is the upper bound (token_budgets.md, phase 2)."""
    if "max_tokens" not in params:
        return params
    limit = params["max_tokens"]
    if ModelSizeClass(model.size_class).thinks:
        limit += model.reasoning_tokens or DEFAULT_REASONING_TOKENS
    if model.max_output_tokens is not None:
        limit = min(limit, model.max_output_tokens)
    return {**params, "max_tokens": limit}


def fit_to_window(
    params: dict[str, Any], prompt_tokens: int, context_length: int
) -> dict[str, Any]:
    """Lower max_tokens so that prompt + answer fit the window. Without
    this Ollama silently cuts the prompt. Raises PromptTooLong if there is
    no useful room left."""
    room = context_length - prompt_tokens
    if room < MIN_ANSWER_TOKENS:
        raise PromptTooLong(
            f"The prompt is too long for the model's window "
            f"(about {prompt_tokens} tokens of {context_length})"
        )
    if "max_tokens" in params and params["max_tokens"] > room:
        return {**params, "max_tokens": room}
    return params
