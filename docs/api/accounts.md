# Accounts API

Account information retrieval operations.

Access via `client.accounts`.

## AccountsAPI

::: ctrader_api_client.api.AccountsAPI
    options:
      show_source: false
      members:
        - get_trader
        - list_by_token
        - resolve_account_id

## Usage Examples

### Get Account Details

```python
account = await client.accounts.get_trader(account_id)

print(f"Balance: {account.balance}")
print(f"Leverage: {account.get_leverage()}")
print(f"Account type: {account.account_type}")
print(f"Broker name: {account.broker_name}")
```

## Account Discovery

The accounts an access token covers can be listed without authenticating any of
them:

```python
# Get all accounts associated with a token
for acc in await client.accounts.list_by_token(access_token):
    print(f"Login: {acc.trader_login}, Account ID: {acc.account_id}")
    print(f"  Live: {acc.is_live}, Broker: {acc.broker_name}")

# Or resolve a single login straight to its account ID
account_id = await client.accounts.resolve_account_id(access_token, trader_login=12345678)
```

## Related

- [Authentication](client.md#authentication) - Authenticating accounts
