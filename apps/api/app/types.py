"""Custom SQLAlchemy column types.

``StrEnumType`` stores a ``StrEnum`` by its *value* and reconstructs the enum
on load. Without it, a column declared ``Mapped[SiteKind]`` over a plain
``String`` returns a bare ``str``, so the annotation lies and every read site
has to defend itself with ``isinstance`` checks or ``str()`` coercion.

SQLAlchemy's built-in ``Enum`` would also work, but it persists the member
*name* (``COOLING_CENTER``) rather than the value (``cooling_center``). The
values are what appear in JSON payloads, WebSocket frames, and audit hashes, so
storing anything else would give the same concept two spellings.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import Dialect, String
from sqlalchemy.types import TypeDecorator


class StrEnumType(TypeDecorator[Any]):
    """Persist a StrEnum as its value; return the enum member on load."""

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[StrEnum], length: int = 32) -> None:
        self.enum_class = enum_class
        super().__init__(length)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        # Accept either the enum or a raw string, so callers and fixtures can
        # pass whichever they have.
        return str(self.enum_class(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> StrEnum | None:
        if value is None:
            return None
        return self.enum_class(value)
