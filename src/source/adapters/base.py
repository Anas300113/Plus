"""Adapter interface: ExternalQuestion -> CanonicalQuestion.
External schemas must never leak into the application."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def to_canonical(self, external: dict[str, Any]) -> dict[str, Any]:
        """Transform one external record into a canonical-question dict."""
        raise NotImplementedError
