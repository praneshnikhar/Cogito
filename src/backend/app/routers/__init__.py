"""Shared router utilities: CORS-safe user/session headers + common payloads."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header

SessionUuid = Annotated[str | None, Header(alias="x-user-id")]


def user_id(x: str | None) -> str | None:
    return (x or "anonymous").strip() or "anonymous"