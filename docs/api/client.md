# Client

The main entry point for interacting with the cTrader API.

## CTraderClient

::: ctrader_api_client.CTraderClient
    options:
      show_source: false
      members:
        - __init__
        - connect
        - close
        - "on"
        - "off"
        - auth
        - accounts
        - symbols
        - trading
        - market_data
        - is_connected
        - protocol

## ClientConfig

::: ctrader_api_client.ClientConfig
    options:
      show_source: false

## Authentication

The `client.auth` property provides access to authentication operations.

::: ctrader_api_client.auth.AuthManager
    options:
      show_source: false
      members:
        - authenticate_app
        - authenticate_account
        - authenticate_by_trader_login
        - get_accounts
        - resolve_account_id
        - get_credentials
        - remove_account
        - is_app_authenticated
        - authenticated_accounts

## AccountCredentials

::: ctrader_api_client.auth.AccountCredentials
    options:
      show_source: false
