"""
DAG Executor — runs agents in dependency order with maximum parallelism.

The executor:
  1. Resolves which agents can run immediately (no pending deps)
  2. Launches them as asyncio tasks
  3. As each agent completes, unlocks the next layer
  4. Retries agents that raise unhandled exceptions (up to agent.max_retries)
  5. Continues until all agents are done or blocked by failed dependencies
"""

import asyncio
import logging
from typing import Type

from agents.base_agent import BaseAgent, AgentContext, AgentResult

_log = logging.getLogger("dag_executor")

_BACKOFF = [0, 1, 2, 4, 8]   # wait seconds before attempt N (index = attempt number)


async def execute_dag(
    agent_classes: list[Type[BaseAgent]],
    context: AgentContext,
    pre_completed: dict[str, AgentResult] | None = None,
) -> dict[str, AgentResult]:
    """
    Execute agent classes respecting their .dependencies.

    pre_completed: agents already finished in a prior run (e.g. CrawlAgent during
                   a revision cycle). Their results are injected as satisfied deps
                   so downstream agents become ready immediately.

    Returns dict of agent_name → AgentResult.
    """
    name_to_class = {cls.name: cls for cls in agent_classes}

    # Seed completed with any pre-finished agents
    completed: dict[str, AgentResult] = dict(pre_completed or {})
    failed:    set[str]               = {n for n, r in completed.items() if not r.success}
    pending:   set[str]               = {cls.name for cls in agent_classes}
    running:   dict[str, asyncio.Task] = {}

    async def _run_agent(cls: Type[BaseAgent]) -> AgentResult:
        agent       = cls(context)
        max_retries = getattr(cls, "max_retries", 3)
        last_error  = ""

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                wait = _BACKOFF[min(attempt - 1, len(_BACKOFF) - 1)]
                _log.warning(
                    "[%s] retry %d/%d after %ds (error: %s)",
                    cls.name, attempt, max_retries, wait, last_error,
                )
                await agent._retry_triggered(attempt, max_retries, last_error)
                await asyncio.sleep(wait)

            try:
                result = await agent.run()
                if result.success:
                    result.retries = attempt - 1
                    # mark any previously recorded errors as recovered
                    from utils.error_manager import error_manager
                    if attempt > 1:
                        error_manager.mark_recovered(context.audit_id, cls.name)
                    return result

                # run() returned failure without raising — treat as final failure
                last_error = result.error or "run() returned success=False"
                break

            except Exception as exc:
                last_error = str(exc)
                if attempt == max_retries:
                    await agent._failed(last_error)

        return AgentResult(
            agent_name=cls.name,
            success=False,
            error=last_error,
            retries=max_retries - 1,
        )

    def _ready() -> list[str]:
        """Agents whose dependencies are all complete and haven't started."""
        return [
            name for name in pending
            if name not in running
            and all(dep in completed for dep in name_to_class[name].dependencies)
            and not any(dep in failed for dep in name_to_class[name].dependencies)
        ]

    while pending or running:
        for name in _ready():
            task = asyncio.create_task(_run_agent(name_to_class[name]))
            running[name] = task

        if not running:
            # Remaining agents are all blocked by failed dependencies
            blocked = list(pending - set(running))
            _log.warning("DAG stalled — blocked agents: %s", blocked)
            break

        done, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            name   = next(n for n, t in running.items() if t is task)
            result: AgentResult = task.result()
            completed[name] = result
            pending.discard(name)
            del running[name]

            if not result.success:
                failed.add(name)
                _log.error(
                    "[%s] permanently failed after %d retries: %s",
                    name, result.retries, result.error,
                )

    return completed
