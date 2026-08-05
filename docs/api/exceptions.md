# Exceptions

Every exception the library raises derives from `CTraderError`, so a single
`except CTraderError` catches anything that came from the client rather than
from your own code.

```python
from ctrader_api_client import CTraderError
```

## Hierarchy

```
CTraderError
├── CTraderConnectionError
│   ├── CTraderConnectionFailedError    could not reach the server
│   ├── CTraderConnectionClosedError    the link went away mid-flight
│   └── CTraderConnectionTimeoutError   a request outlived its timeout
├── AuthenticationError
│   ├── ApplicationAuthError            the server rejected client_id/secret
│   ├── AccountAuthError                the server rejected the account
│   ├── TokenExpiredError               the access token is expired or invalid
│   ├── TokenRefreshError               a refresh exhausted its retries
│   └── AccountNotFoundError            no account matches that trader login
├── APIError                            an error response to a request
└── ProtocolError
    ├── FramingError                    a frame that cannot be on the wire
    ├── DeserializationError            a payload that will not parse
    └── UnknownPayloadTypeError         a payload type this version cannot map
```

## What each call raises

### Entering the client

```python
from ctrader_api_client import ApplicationAuthError, CTraderConnectionFailedError

try:
    async with CTraderClient(config) as client:
        ...
except CTraderConnectionFailedError as e:
    print(f"Could not reach {e.host}:{e.port}: {e.cause}")
except ApplicationAuthError as e:
    print(f"Application rejected: {e.error_code} - {e.description}")
```

Bringing the client up connects the transport and authenticates the
application, so those are the two failures `async with` raises. A client that
cannot do both does not open.

Exceptions leave the block as themselves. Write `except CTraderError`, not
`except*`. If several background tasks fail at once the block raises an
`ExceptionGroup`, because that is genuinely what happened; a single failure is
never wrapped in one.

### Authenticating an account

```python
from ctrader_api_client import AccountAuthError, TokenExpiredError

try:
    await client.auth.authenticate_trader(credentials)
except TokenExpiredError:
    credentials = await my_oauth_flow.reauthorize(account_id)
    await client.auth.authenticate_trader(credentials)
except AccountAuthError as e:
    print(f"Account {e.ctid_trader_account_id} rejected: {e.error_code}")
```

`TokenExpiredError` covers both a token the client knows has expired and one the
server rejects as invalid. Neither can be retried back to life — it needs a new
token.

### Requests

Any call on `client.trading`, `client.symbols`, `client.accounts` or
`client.market_data` can raise:

- `APIError` — the server answered with an error.
- `CTraderConnectionTimeoutError` — no answer inside the timeout.
- `CTraderConnectionClosedError` — the link died while the request was in
  flight.

```python
from ctrader_api_client import APIError, CTraderConnectionTimeoutError

try:
    await client.trading.place_order(account_id, request)
except APIError as e:
    if e.is_rate_limited():
        await anyio.sleep(e.retry_after or 1)
    elif e.is_maintenance():
        ...  # the server is down until e.maintenance_end_timestamp
    else:
        raise
except CTraderConnectionTimeoutError as e:
    print(f"{e.operation} gave up after {e.timeout_seconds}s")
```

`APIError` carries the server's own `error_code` and `description`, plus three
questions worth asking before deciding whether to retry:

- `is_rate_limited()` — back off; `retry_after` says how long if the server said.
- `is_maintenance()` — the server is down for maintenance, not broken.
- `is_token_failure()` — the token is the problem rather than the application,
  the account or the request, so a retry cannot help.

## Failures reported as events

Not every failure can be raised, because not everything happens inside a call
you made. Three arrive as events instead:

| Event | Meaning |
| --- | --- |
| `TokenRefreshFailedEvent` | A refresh exhausted its retries. Carries a `TokenRefreshError`. The credentials are kept and retried on the next check interval, so a repeat means the refresh token is dead. |
| `SubscriptionRestoreFailedEvent` | Standing subscriptions could not be re-applied to a re-established session. The account is missing market data until the next reconnection. |
| `ReconnectedEvent` | Carries `failed_accounts` alongside `restored_accounts`, for accounts that could not be re-authenticated on the new link. |

```python
from ctrader_api_client import TokenRefreshFailedEvent


@client.on(TokenRefreshFailedEvent, account_id=account_id)
async def on_refresh_failed(event: TokenRefreshFailedEvent):
    logger.error("Refresh failed for %d: %s", event.account_id, event.error.cause)
```

Exceptions raised inside your own event handlers are logged and do not stop the
other handlers for that event.

## Reference

::: ctrader_api_client.CTraderError
    options:
      show_source: false

### Connection

::: ctrader_api_client.CTraderConnectionError
    options:
      show_source: false

::: ctrader_api_client.CTraderConnectionFailedError
    options:
      show_source: false

::: ctrader_api_client.CTraderConnectionClosedError
    options:
      show_source: false

::: ctrader_api_client.CTraderConnectionTimeoutError
    options:
      show_source: false

### Authentication

::: ctrader_api_client.AuthenticationError
    options:
      show_source: false

::: ctrader_api_client.ApplicationAuthError
    options:
      show_source: false

::: ctrader_api_client.AccountAuthError
    options:
      show_source: false

::: ctrader_api_client.TokenExpiredError
    options:
      show_source: false

::: ctrader_api_client.TokenRefreshError
    options:
      show_source: false

::: ctrader_api_client.AccountNotFoundError
    options:
      show_source: false

### API

::: ctrader_api_client.APIError
    options:
      show_source: false
      members:
        - is_rate_limited
        - is_maintenance
        - is_token_failure

### Protocol

::: ctrader_api_client.ProtocolError
    options:
      show_source: false

::: ctrader_api_client.FramingError
    options:
      show_source: false

::: ctrader_api_client.DeserializationError
    options:
      show_source: false

::: ctrader_api_client.UnknownPayloadTypeError
    options:
      show_source: false

## Related

- [Events](events.md) - Failures reported as events
- [Client](client.md) - Client lifecycle and authentication
