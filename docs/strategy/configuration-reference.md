# Strategy Configuration Reference

The configured instance is `config/strategies/nifty-long-gamma-v1.yaml`. Pydantic models under `backend/app/strategy/` define its strict schema. Unknown and missing fields fail validation.

Identity fields are `strategy_id`, `strategy_version`, `schema_version`, and `created_at`. The content hash excludes `created_at` and includes every behavioral field. Canonical JSON uses sorted UTF-8 keys, no insignificant whitespace, and normalized decimal text for floating-point configuration values before SHA-256 hashing.

`underlying`, `signal`, `entry`, `expiry`, `strike`, and `position` freeze instrument and construction semantics. `hedging` includes the complete benchmark set and typed parameters for every policy. `exit.precedence` is complete and ordered. `risk` requires every lockout and limit explicitly.

The strategy contract does not define synthetic exchange mechanics. `config/simulation/nifty-synthetic-market-v1.yaml` is the separate simulation-market contract for the trading-session clock, eligible expiry sessions, strike grid, liquidity assumptions, option and futures multipliers, futures identity and delta, and synthetic spread inputs. Unknown or missing market fields fail validation, and every field is included in the market hash and simulation run contract.

Validate from `backend`:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.validate_strategy_config \
  --config ../config/strategies/nifty-long-gamma-v1.yaml
```
