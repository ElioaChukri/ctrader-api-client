"""What an API error response tells a caller."""

from __future__ import annotations

from ctrader_api_client._internal.proto import ProtoOAErrorRes
from ctrader_api_client.exceptions import APIError


def test_the_error_code_and_description_reach_the_caller() -> None:
    error = APIError.from_proto(ProtoOAErrorRes(error_code="NOT_ENOUGH_MONEY", description="Insufficient funds"))

    assert error.error_code == "NOT_ENOUGH_MONEY"
    assert error.description == "Insufficient funds"


def test_the_error_message_identifies_the_failing_account() -> None:
    error = APIError.from_proto(ProtoOAErrorRes(error_code="NOT_ENOUGH_MONEY", ctid_trader_account_id=12345))

    assert "NOT_ENOUGH_MONEY" in str(error)
    assert "12345" in str(error)


def test_omitted_fields_are_absent_rather_than_zero() -> None:
    """Proto sends 0 for "not set"; reporting account 0 or a 1970 timestamp would be a lie."""
    error = APIError.from_proto(ProtoOAErrorRes(error_code="OA_AUTH_TOKEN_EXPIRED"))

    assert error.description is None
    assert error.ctid_trader_account_id is None
    assert error.maintenance_end_timestamp is None
    assert error.retry_after is None


def test_a_frequency_error_is_recognised_as_rate_limiting() -> None:
    error = APIError.from_proto(ProtoOAErrorRes(error_code="REQUEST_FREQUENCY_EXCEEDED"))

    assert error.is_rate_limited()


def test_a_retry_after_hint_marks_the_error_as_rate_limiting() -> None:
    """The server signals throttling by hint as well as by code."""
    error = APIError.from_proto(ProtoOAErrorRes(error_code="SOMETHING_ELSE", retry_after=30))

    assert error.is_rate_limited()
    assert error.retry_after == 30


def test_an_unrelated_error_is_not_rate_limiting() -> None:
    error = APIError.from_proto(ProtoOAErrorRes(error_code="NOT_ENOUGH_MONEY"))

    assert not error.is_rate_limited()


def test_a_maintenance_error_is_recognised() -> None:
    error = APIError.from_proto(ProtoOAErrorRes(error_code="SERVER_IS_UNDER_MAINTENANCE"))

    assert error.is_maintenance()


def test_a_maintenance_window_marks_the_error_as_maintenance() -> None:
    error = APIError.from_proto(
        ProtoOAErrorRes(error_code="SOMETHING_ELSE", maintenance_end_timestamp=1_700_000_000_000)
    )

    assert error.is_maintenance()
    assert error.maintenance_end_timestamp == 1_700_000_000_000


def test_an_unrelated_error_is_not_maintenance() -> None:
    error = APIError.from_proto(ProtoOAErrorRes(error_code="NOT_ENOUGH_MONEY"))

    assert not error.is_maintenance()
