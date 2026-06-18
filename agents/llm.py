"""LangChain ChatOpenAI LLM wrapper for the AI pipeline."""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class LLMWrapper:
    """Wraps LangChain ChatOpenAI to support the existing config schema.

    Reads configuration keys from a dict matching ``scivision_config.yaml``:

    - ``llm_model`` — model name (e.g. ``"kimi-k2.5"``)
    - ``llm_base_url`` — custom base URL
    - ``llm_temperature`` — generation temperature (default ``0.2``)
    - ``llm_max_tokens`` — max output tokens (default ``30000``)
    - ``llm_timeout_sec`` — request timeout in seconds (default ``1200``)
    - ``llm_api_key_env`` — env var name for the API key (default ``"OPENAI_API_KEY"``)
    - ``llm_api_key`` — fallback literal API key (only used when the env var is empty)
    """

    def __init__(self, config: dict) -> None:
        self.model: str = config.get("llm_model", "kimi-k2.5")
        self.base_url: str = config.get(
            "llm_base_url",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.temperature: float = float(config.get("llm_temperature", 0.2))
        self.max_tokens: int = int(config.get("llm_max_tokens", 30000))
        self.timeout: int = int(config.get("llm_timeout_sec", 1200))

        api_key_env: str = config.get("llm_api_key_env", "OPENAI_API_KEY")
        self.api_key: str = os.environ.get(api_key_env, config.get("llm_api_key", ""))

        self._chat_model: ChatOpenAI | None = None

    # ------------------------------------------------------------------
    # Lazy-init accessor
    # ------------------------------------------------------------------
    def get_chat_model(self) -> ChatOpenAI:
        """Return a configured ``ChatOpenAI`` instance (lazy initialised)."""
        if self._chat_model is None:
            self._chat_model = ChatOpenAI(
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
                api_key=self.api_key,
            )
        return self._chat_model

    # ------------------------------------------------------------------
    # Public invoke helpers (all wrapped with 3-retry exponential backoff)
    # ------------------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def invoke(self, messages: list[dict], **kwargs: Any) -> str:
        """Direct LLM call.  Returns the response content string."""
        model = self.get_chat_model()
        response = model.invoke(messages, **kwargs)
        return response.content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def invoke_with_tools(
        self, messages: list[dict], tools: list[dict], **kwargs: Any
    ) -> dict:
        """Function-calling call.  Returns the full response message dict."""
        model = self.get_chat_model().bind_tools(tools)
        response = model.invoke(messages, **kwargs)
        return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def invoke_structured(
        self,
        messages: list[dict],
        output_schema: type,
        **kwargs: Any,
    ) -> Any:
        """Structured output via ``.with_structured_output()``.

        Args:
            messages: Conversation history.
            output_schema: A Pydantic ``BaseModel`` subclass.
            **kwargs: Forwarded to ``with_structured_output()``.

        Returns:
            An instance of ``output_schema``.
        """
        from pydantic import BaseModel

        if not (isinstance(output_schema, type) and issubclass(output_schema, BaseModel)):
            raise TypeError("output_schema must be a Pydantic BaseModel subclass")

        model = self.get_chat_model().with_structured_output(
            output_schema,
            method="json_mode",
            **kwargs,
        )
        return model.invoke(messages)
