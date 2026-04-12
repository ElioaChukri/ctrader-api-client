from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base class for all immutable models.

    All models derived from this class are:
    - Frozen (immutable after creation)
    - Strict (no type coercion)
    - Forbid extra fields
    """

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
    )
