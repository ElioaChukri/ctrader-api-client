# Symbols API

Symbol information lookup and search operations.

Access via `client.symbols`.

## SymbolsAPI

::: ctrader_api_client.api.SymbolsAPI
    options:
      show_source: false
      members:
        - list_all
        - get_by_ids
        - get_by_id
        - search

## Usage Examples

### List All Symbols

```python
# Get lightweight info for all symbols
symbols = await client.symbols.list_all(account_id)

for sym in symbols:
    print(f"{sym.symbol_id}: {sym.symbol_name}")
```

### Get Symbol by ID

```python
# Get full symbol details
symbol = await client.symbols.get_by_id(account_id, 270)

print(f"Name: {symbol.symbol_name}")
print(f"Digits: {symbol.digits}")
print(f"Lot size: {symbol.lot_size}")
print(f"Min volume: {symbol.min_volume}")
print(f"Max volume: {symbol.max_volume}")
```

### Get Multiple Symbols

```python
symbols = await client.symbols.get_by_ids(account_id, [270, 271, 272])

for sym in symbols:
    print(f"{sym.symbol_name}: {sym.digits} digits")
```

### Search Symbols

```python
# Find all EUR pairs
eur_pairs = await client.symbols.search(account_id, "EUR")

for sym in eur_pairs:
    print(sym.symbol_name)
```

## Price Conversion

Prices in the cTrader API are represented as integers (e.g. 12345 for 1.2345) and the decimal place varies from one symbol to another.
Use `Symbol` methods to convert between price and decimal:

```python
symbol = await client.symbols.get_by_id(account_id, 270)

# Price to decimal
decimal_price = symbol.price_to_decimal(12345)  # 1.2345

# Decimal to price
price = symbol.decimal_to_price(1.2345)  # 12345

```


## Volume Conversion

Use `Symbol` methods to convert between lots and volume:

```python
symbol = await client.symbols.get_by_id(account_id, 270)

# Lots to volume (cents)
volume = symbol.lots_to_volume(1.0)  # 100000

# Volume to lots
lots = symbol.volume_to_lots(100000)  # 1.0
```
