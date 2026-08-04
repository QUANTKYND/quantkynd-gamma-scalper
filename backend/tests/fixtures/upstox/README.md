# Upstox BOD NSE Catalogue Fixtures

This directory contains a schema-faithful sanitized fixture for DATA-1.2.

## Source Schema

The fixture models the approved Upstox BOD NSE `NSE.json.gz` contract for `upstox-nse-nifty-index-derivatives-v1`:

- one top-level JSON array;
- `instrument_key`;
- `segment`;
- `exchange`;
- `instrument_type`;
- `underlying_key`;
- `underlying_type`;
- `underlying_symbol`;
- `expiry` as epoch milliseconds;
- `strike_price`;
- `lot_size`;
- `tick_size` in paise;
- `trading_symbol`;
- `weekly`;
- `minimum_lot`;
- `freeze_quantity`;
- `exchange_token`;
- `name`.

## Sanitization

This is not a real provider file. It is generated from the approved field contract with synthetic provider keys and `SANITIZED_*` token values. No Upstox access token, account identifier, private provider URL, or proprietary full instrument catalogue is present.

The fixture keeps the official field names and unit semantics needed by DATA-1.2. `exchange_token` is retained only as a sanitized provenance field and is never used as provider identity.

## Regeneration

Run the accepted fixture regeneration from the repository root:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python tests/fixtures/upstox/regenerate_fixture.py
```

The gzip file is deterministic because the generator uses an empty gzip filename and `mtime=0`.

Generate hostile local fixtures into a scratch directory with:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python tests/fixtures/upstox/generate_hostile_fixtures.py --output-dir /tmp/quantkynd-data12-hostile-fixtures
```

The hostile generator derives malformed-underlying, conflicting-provider-key, and invalid-tick-size variants from `NSE.canonical.json`. The generated hostile gzip files are for local acceptance only and are not committed.

## Expected Hashes

Current expected hashes:

```text
NSE.canonical.json sha256:73021afd2e45483d099b1ce7afb85595f48b27d3e749b41fe264ff2b8eff27d7
NSE.json.gz sha256:4d05c652e8ab0ae6e24a8cb8bbb3712ed8ff142ef7e542c5c821853f797eb6e7
regenerate_fixture.py sha256:bab6bcfd5ac773bd2781237f7435cbeffe20e30d2bf3aa3c8eaee1879cd942e7
generate_hostile_fixtures.py sha256:e9da5dba86ec06f265c3b5c3c75471bf68c397b1a1ad98bb937af67c6409c4d5
```

Update these values only after regenerating from the committed canonical JSON source.

## Legal And Redaction Constraints

Real provider BOD files must not be committed. Local acceptance may be run with a user-supplied official `NSE.json.gz`, but repository acceptance uses this schema-faithful sanitized fixture.
