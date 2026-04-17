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
    print(f"{sym.symbol_id}: {sym.name}")
```

### Get Symbol by ID

```python
# Get full symbol details
symbol = await client.symbols.get_by_id(account_id, 270)

print(f"Digits: {symbol.digits}")
print(f"Lot size: {symbol.lot_size}")
print(f"Min volume: {symbol.min_volume}")
print(f"Max volume: {symbol.max_volume}")
```

### Get Multiple Symbols

```python
symbols = await client.symbols.get_by_ids(account_id, [270, 271, 272])

for sym in symbols:
    print(f"{sym.name}: {sym.digits} digits, lot_size={sym.lot_size}")
```

### Search Symbols

```python
# Find all EUR pairs
eur_pairs = await client.symbols.search(account_id, "EUR")

for sym in eur_pairs:
    print(sym.name)
```

## Volume Conversion

The cTrader API uses volume in "cents" (smallest volume units). The relationship between lots and volume depends on the symbol's `lot_size`:

```python
symbol = await client.symbols.get_by_id(account_id, 270)

# Lots to volume (for placing orders)
volume = symbol.lots_to_volume(1.0)    # e.g., 10000000 for standard forex

# Volume to lots (for display)
lots = symbol.volume_to_lots(10000000)   # e.g., 1.0 for standard forex
```

**Note:** Different instruments have different lot sizes. Always use the symbol's methods for conversion:

```python
# Standard forex (lot_size=100000)
forex_symbol = await client.symbols.get_by_id(account_id, 1)  # EURUSD (lot_size=10000000)
forex_volume = forex_symbol.lots_to_volume(0.1)  # 1000000

# Index CFD might have different lot_size
index_symbol = await client.symbols.get_by_id(account_id, 270)  # US500 (lot_size=100)
index_volume = index_symbol.lots_to_volume(0.1)  # 10
```
