"""Alert sink protocol — interface for alert delivery."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from whale_detector.models import Alert


@runtime_checkable
class AlertSink(Protocol):
    """Protocol for alert delivery targets."""

    async def send(self, alert: Alert) -> None: ...
