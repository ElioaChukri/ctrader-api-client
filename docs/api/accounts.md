# Accounts API

Account information retrieval operations.

Access via `client.accounts`.

## AccountsAPI

::: ctrader_api_client.api.AccountsAPI
    options:
      show_source: false
      members:
        - get_trader

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

To discover available accounts for an access token, use the auth manager:

```python
# Get all accounts associated with a token
accounts = await client.auth.get_accounts(access_token)

for acc in accounts:
    print(f"Login: {acc.trader_login}, Account ID: {acc.account_id}")
    print(f"  Live: {acc.is_live}, Broker: {acc.broker_name}")
```

## Related

- [Authentication](client.md#authentication) - Authenticating accounts
