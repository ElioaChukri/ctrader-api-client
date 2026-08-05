# Client

The main entry point for interacting with the cTrader API.

A client is used inside `async with`. The block owns the connection and the
background tasks that keep it alive, so leaving it — normally or by exception —
winds them down, and a background task that dies is raised at the end of the
block rather than discovered later.

## CTraderClient

::: ctrader_api_client.CTraderClient
    options:
      show_source: false
      members:
        - __init__
        - from_graph
        - "on"
        - "off"
        - auth
        - accounts
        - symbols
        - trading
        - market_data
        - is_connected
        - protocol

## Composition

`CTraderClient(config)` assembles its own collaborators, which is all most
callers need. When you have to substitute one of them, assemble the graph
yourself and hand it over:

```python
from ctrader_api_client import CTraderClient
from ctrader_api_client.composition import build_graph

graph = build_graph(config, clock=my_clock)
client = CTraderClient.from_graph(graph)
```

::: ctrader_api_client.composition.build_graph
    options:
      show_source: false

::: ctrader_api_client.composition.ClientGraph
    options:
      show_source: false

## ClientConfig

::: ctrader_api_client.ClientConfig
    options:
      show_source: false

## Authentication Policies

Token-refresh and session-recovery timing, passed via
`ClientConfig(refresh_policy=..., reauth_policy=...)`.

::: ctrader_api_client.auth.RefreshPolicy
    options:
      show_source: false

::: ctrader_api_client.auth.ReauthPolicy
    options:
      show_source: false

## Authentication

The `client.auth` property provides access to authentication operations. The
application is authenticated as the client connects, so what is left here is
authenticating trading accounts and asking after the sessions they hold.

::: ctrader_api_client.auth.AuthManager
    options:
      show_source: false
      members:
        - authenticate_trader
        - is_account_authorized
        - get_credentials
        - all_credentials
        - remove_account
        - is_app_authenticated
        - authenticated_accounts
        - authorized_accounts

## AccountCredentials

::: ctrader_api_client.auth.AccountCredentials
    options:
      show_source: false

## TokenStore

Passed as `CTraderClient(config, token_store=...)`. cTrader rotates both tokens
on every refresh and invalidates the old pair immediately, so a process that
restarts holding the pair it was originally given can no longer authenticate.

::: ctrader_api_client.auth.TokenStore
    options:
      show_source: false
      members: true

The contract is write-only, because writing is the half the client has to do for
you: rotation happens mid-session, at a moment you cannot observe. Reading back at
startup is yours, since only you know which accounts a given process is
responsible for. Nothing stops the same class from doing both:

```python
class PostgresTokenStore(TokenStore):
    async def save(self, credentials: AccountCredentials) -> None:
        ...  # required by the protocol, called by the client

    async def load(self, account_id: int) -> AccountCredentials | None:
        ...  # not part of the protocol, called by you at startup


store = PostgresTokenStore(pool)
client = CTraderClient(config, token_store=store)

async with client:
    stored = await store.load(account_id)
    if stored is None:
        stored = AccountCredentials(
            account_id=account_id,
            access_token="your_access_token",
            refresh_token="your_refresh_token",
            expires_at=1778617423,
        )

    await client.auth.authenticate_trader(stored)
```
