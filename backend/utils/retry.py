"""Centralized retry configurations using tenacity."""

import logging
from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

_log = logging.getLogger("retry")


def http_retry(max_attempts: int = 3) -> AsyncRetrying:
    """Exponential backoff for HTTP requests: 0.5 s → 5 s."""
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(_log, logging.WARNING),
        reraise=True,
    )


def llm_retry(max_attempts: int = 2) -> AsyncRetrying:
    """Exponential backoff for LLM API calls: 2 s → 15 s."""
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=2, min=2, max=15),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(_log, logging.WARNING),
        reraise=True,
    )


def agent_retry(max_attempts: int = 3) -> AsyncRetrying:
    """Exponential backoff for full agent run() calls: 1 s → 10 s."""
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(_log, logging.WARNING),
        reraise=True,
    )


__all__ = ["http_retry", "llm_retry", "agent_retry", "RetryError"]
