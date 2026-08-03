from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..events import HealthEvent


class NotifierError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Notifier(Protocol):
    """A destination that turns AWS Health events into tracked tickets.

    Implementations are sink-specific (Jira, GitHub Issues today). The handler
    stays sink-agnostic and talks only to this interface.
    """

    def open(self, ev: HealthEvent, cfg: Config) -> str:
        """Create a ticket for an active event and return its external ref."""
        ...

    def close(self, ref: str, cfg: Config) -> None:
        """Resolve the ticket identified by ref when the event ends."""
        ...
