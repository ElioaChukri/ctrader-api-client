from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_protocol() -> MagicMock:
    """Create a mock Protocol instance."""
    protocol = MagicMock()
    protocol.send_request = AsyncMock()
    return protocol
