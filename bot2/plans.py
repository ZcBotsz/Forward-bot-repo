"""Subscription and access-control helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from .config import FEATURE_PLANS, plan_at_least
from .ui import button, markup, sc

P = ParamSpec("P")
R = TypeVar("R")


def can_use(user: dict[str, Any] | None, feature: str) -> bool:
    if not user or user.get("banned"):
        return False
    return plan_at_least(str(user.get("plan", "free")), FEATURE_PLANS[feature])


def lock_text(feature: str) -> str:
    required = FEATURE_PLANS[feature]
    return sc(f"🔒 This feature needs the {required.title()} plan. Tap Plans to upgrade.")


async def require_feature(query_or_message: Any, services: Any, feature: str) -> bool:
    """Respond with a guarded upgrade action and return False if access is denied."""
    from_user = query_or_message.from_user
    user = await services.db.get_user(from_user.id)
    if can_use(user, feature):
        return True
    destination = getattr(query_or_message, "message", query_or_message)
    await destination.reply_text(
        lock_text(feature),
        reply_markup=markup([[button(from_user.id, "💳 Plans", "plans:home")]]),
    )
    # Callback queries otherwise keep Telegram's loading spinner active.
    answer = getattr(query_or_message, "answer", None)
    if answer:
        await answer()
    return False


def requires(feature: str) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | None]]]:
    """Optional handler decorator for the places a simple access guard is appropriate."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
        @wraps(func)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R | None:
            # Registered handlers conventionally receive (client, update, services) or bind services.
            update = args[1] if len(args) > 1 else kwargs.get("update")
            services = kwargs.get("services")
            if services is None and args:
                services = getattr(args[0], "services", None)
            if services is None or update is None:
                raise RuntimeError("@requires needs a services-aware handler")
            if not await require_feature(update, services, feature):
                return None
            return await func(*args, **kwargs)

        return wrapped

    return decorator
