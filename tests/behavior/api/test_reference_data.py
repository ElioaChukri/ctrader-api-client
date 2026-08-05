"""Reading account and symbol reference data."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAApplicationAuthRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOALightSymbol,
    ProtoOASymbol,
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
    ProtoOATrader,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ctrader_api_client.api import AccountsAPI, SymbolsAPI
from ctrader_api_client.exceptions import AccountNotFoundError, APIError, TokenExpiredError

from ...harness import StubProtocol, factories


def trader(**overrides: object) -> ProtoOATrader:
    fields: dict[str, object] = {
        "ctid_trader_account_id": factories.ACCOUNT_ID,
        "balance": 1_000_000,
        "money_digits": 2,
        "leverage_in_cents": 10_000,
        "trader_login": factories.TRADER_LOGIN,
        "deposit_asset_id": 1,
    }
    fields.update(overrides)
    return ProtoOATrader(**fields)  # type: ignore[arg-type]


def light_symbol(symbol_id: int = factories.SYMBOL_ID, name: str = "EURUSD") -> ProtoOALightSymbol:
    return ProtoOALightSymbol(
        symbol_id=symbol_id,
        symbol_name=name,
        enabled=True,
        base_asset_id=1,
        quote_asset_id=2,
        symbol_category_id=1,
        description=f"{name} spot",
    )


def full_symbol(symbol_id: int = factories.SYMBOL_ID, **overrides: object) -> ProtoOASymbol:
    fields: dict[str, object] = {
        "symbol_id": symbol_id,
        "digits": 5,
        "pip_position": 4,
        "lot_size": 10_000_000,
        "min_volume": 100_000,
        "max_volume": 1_000_000_000,
        "step_volume": 100_000,
        "enable_short_selling": True,
        "trading_mode": 0,
    }
    fields.update(overrides)
    return ProtoOASymbol(**fields)  # type: ignore[arg-type]


async def test_the_requested_account_is_returned(accounts: AccountsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOATraderReq, ProtoOATraderRes(trader=trader()))

    account = await accounts.get_trader(factories.ACCOUNT_ID)

    assert account.account_id == factories.ACCOUNT_ID
    assert account.balance == Decimal("10000.00")
    assert account.get_leverage() == "1:100"


async def test_the_account_request_names_the_account(accounts: AccountsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOATraderReq, ProtoOATraderRes(trader=trader()))

    await accounts.get_trader(factories.ACCOUNT_ID)

    assert protocol.only_sent(ProtoOATraderReq).ctid_trader_account_id == factories.ACCOUNT_ID


async def test_an_account_error_reaches_the_caller(accounts: AccountsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOATraderReq, APIError(error_code="CH_CTID_TRADER_ACCOUNT_NOT_FOUND"))

    with pytest.raises(APIError) as exc_info:
        await accounts.get_trader(factories.ACCOUNT_ID)

    assert exc_info.value.error_code == "CH_CTID_TRADER_ACCOUNT_NOT_FOUND"


async def test_an_unexpected_account_reply_is_an_error(accounts: AccountsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOATraderReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await accounts.get_trader(factories.ACCOUNT_ID)

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


async def test_accounts_are_listed_for_an_access_token(accounts: AccountsAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(
            factories.ctid_account(account_id=1, trader_login=111),
            factories.ctid_account(account_id=2, trader_login=222),
        ),
    )

    listed = await accounts.list_by_token(factories.ACCESS_TOKEN)

    assert [account.account_id for account in listed] == [1, 2]
    assert [account.trader_login for account in listed] == [111, 222]


async def test_the_account_list_request_carries_the_token(accounts: AccountsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAGetAccountListByAccessTokenReq, factories.account_list_res())

    await accounts.list_by_token(factories.ACCESS_TOKEN)

    assert protocol.only_sent(ProtoOAGetAccountListByAccessTokenReq).access_token == factories.ACCESS_TOKEN


async def test_a_trader_login_resolves_to_its_account_id(accounts: AccountsAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(
            factories.ctid_account(account_id=1, trader_login=111),
            factories.ctid_account(account_id=2, trader_login=222),
        ),
    )

    account_id = await accounts.resolve_account_id(factories.ACCESS_TOKEN, trader_login=222)

    assert account_id == 2


async def test_an_unknown_trader_login_reports_what_is_available(
    accounts: AccountsAPI,
    protocol: StubProtocol,
) -> None:
    """The caller most likely typed the wrong login, so name the ones that exist."""
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(
            factories.ctid_account(account_id=1, trader_login=111),
            factories.ctid_account(account_id=2, trader_login=222),
        ),
    )

    with pytest.raises(AccountNotFoundError) as exc_info:
        await accounts.resolve_account_id(factories.ACCESS_TOKEN, trader_login=999)

    assert exc_info.value.trader_login == 999
    assert exc_info.value.available_logins == [111, 222]
    assert "111" in str(exc_info.value)


async def test_an_unexpected_reply_to_the_account_list_is_an_error(
    accounts: AccountsAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAGetAccountListByAccessTokenReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await accounts.list_by_token(factories.ACCESS_TOKEN)

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


async def test_listing_accounts_with_a_dead_token_reports_it_as_expired(
    accounts: AccountsAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        APIError(error_code="CH_ACCESS_TOKEN_INVALID"),
    )

    with pytest.raises(TokenExpiredError):
        await accounts.list_by_token(factories.ACCESS_TOKEN)


async def test_listing_accounts_surfaces_other_failures_unchanged(
    accounts: AccountsAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        APIError(error_code="CH_OA_CLIENT_NOT_FOUND"),
    )

    with pytest.raises(APIError) as exc_info:
        await accounts.list_by_token(factories.ACCESS_TOKEN)

    assert exc_info.value.error_code == "CH_OA_CLIENT_NOT_FOUND"


async def test_every_listed_symbol_is_returned(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOASymbolsListReq,
        ProtoOASymbolsListRes(symbol=[light_symbol(270, "EURUSD"), light_symbol(271, "GBPUSD")]),
    )

    listed = await symbols.list_all(factories.ACCOUNT_ID)

    assert [(s.symbol_id, s.name) for s in listed] == [(270, "EURUSD"), (271, "GBPUSD")]


async def test_an_empty_symbol_list_is_returned_as_such(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOASymbolsListReq, ProtoOASymbolsListRes(symbol=[]))

    assert await symbols.list_all(factories.ACCOUNT_ID) == []


async def test_a_symbol_search_matches_case_insensitively(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOASymbolsListReq,
        ProtoOASymbolsListRes(
            symbol=[light_symbol(270, "EURUSD"), light_symbol(271, "GBPUSD"), light_symbol(272, "BTCEUR")]
        ),
    )

    found = await symbols.search(factories.ACCOUNT_ID, "eur")

    assert [s.name for s in found] == ["EURUSD", "BTCEUR"]


async def test_a_search_with_no_matches_returns_nothing(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOASymbolsListReq, ProtoOASymbolsListRes(symbol=[light_symbol(270, "EURUSD")]))

    assert await symbols.search(factories.ACCOUNT_ID, "XAU") == []


async def test_symbols_are_fetched_by_id(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOASymbolByIdReq,
        ProtoOASymbolByIdRes(symbol=[full_symbol(270), full_symbol(271)]),
    )

    fetched = await symbols.get_by_ids(factories.ACCOUNT_ID, [270, 271])

    assert [s.symbol_id for s in fetched] == [270, 271]


async def test_the_symbol_request_lists_the_wanted_ids(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOASymbolByIdReq, ProtoOASymbolByIdRes(symbol=[full_symbol(270)]))

    await symbols.get_by_ids(factories.ACCOUNT_ID, [270, 271])

    request = protocol.only_sent(ProtoOASymbolByIdReq)
    assert request.ctid_trader_account_id == factories.ACCOUNT_ID
    assert request.symbol_id == [270, 271]


async def test_a_single_symbol_is_unwrapped(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOASymbolByIdReq, ProtoOASymbolByIdRes(symbol=[full_symbol(270, digits=3)]))

    symbol = await symbols.get_by_id(factories.ACCOUNT_ID, 270)

    assert symbol.symbol_id == 270
    assert symbol.digits == 3


async def test_asking_for_a_symbol_the_server_does_not_know_is_an_error(
    symbols: SymbolsAPI,
    protocol: StubProtocol,
) -> None:
    """Returning nothing would push the empty case onto every caller."""
    protocol.respond(ProtoOASymbolByIdReq, ProtoOASymbolByIdRes(symbol=[]))

    with pytest.raises(ValueError, match="270"):
        await symbols.get_by_id(factories.ACCOUNT_ID, 270)


async def test_an_unexpected_symbol_list_reply_is_an_error(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOASymbolsListReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await symbols.list_all(factories.ACCOUNT_ID)

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


async def test_an_unexpected_symbol_detail_reply_is_an_error(symbols: SymbolsAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOASymbolByIdReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await symbols.get_by_ids(factories.ACCOUNT_ID, [270])

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"
