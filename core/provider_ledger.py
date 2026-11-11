"""Request-scoped health reporting for retrieval providers and lanes."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, Iterator, List, Optional


class ProviderStatus(str, Enum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    TIMEOUT = "TIMEOUT"
    PROVIDER_DOWN = "PROVIDER_DOWN"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


@dataclass
class ProviderEvent:
    lane: str
    provider: str
    status: ProviderStatus
    result_count: int = 0
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {
            "lane": self.lane,
            "provider": self.provider,
            "status": self.status.value,
            "result_count": self.result_count,
        }
        if self.message:
            value["message"] = self.message
        return value


@dataclass
class ProviderHealthLedger:
    events: List[ProviderEvent] = field(default_factory=list)

    def record(
        self,
        lane: str,
        provider: str,
        status: ProviderStatus,
        result_count: int = 0,
        message: Optional[str] = None,
    ) -> None:
        safe_message = _sanitize_message(message)
        self.events.append(
            ProviderEvent(
                lane=lane,
                provider=provider,
                status=status,
                result_count=max(0, int(result_count)),
                message=safe_message,
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        degraded_statuses = {
            ProviderStatus.TIMEOUT,
            ProviderStatus.PROVIDER_DOWN,
            ProviderStatus.ERROR,
        }
        degraded = any(event.status in degraded_statuses for event in self.events)
        return {
            "status": "degraded" if degraded else "ok",
            "events": [event.to_dict() for event in self.events[-50:]],
        }


_CURRENT_LEDGER: ContextVar[Optional[ProviderHealthLedger]] = ContextVar(
    "retrieval_provider_ledger", default=None
)
_CURRENT_LANE: ContextVar[str] = ContextVar("retrieval_provider_lane", default="unassigned")


def _sanitize_message(message: Optional[str]) -> Optional[str]:
    if not message:
        return None
    clean = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+|(?:api[_ -]?key|token|secret)\s*[:=]\s*)\S+",
        r"\1[redacted]",
        str(message),
    )
    return clean.strip()[:240] or None


@contextmanager
def retrieval_lane_scope(
    ledger: ProviderHealthLedger,
    lane: str,
) -> Iterator[None]:
    ledger_token = _CURRENT_LEDGER.set(ledger)
    lane_token = _CURRENT_LANE.set(lane)
    try:
        yield
    finally:
        _CURRENT_LANE.reset(lane_token)
        _CURRENT_LEDGER.reset(ledger_token)


def record_provider_event(
    provider: str,
    status: ProviderStatus,
    result_count: int = 0,
    message: Optional[str] = None,
) -> None:
    ledger = _CURRENT_LEDGER.get()
    if ledger is not None:
        ledger.record(
            lane=_CURRENT_LANE.get(),
            provider=provider,
            status=status,
            result_count=result_count,
            message=message,
        )
