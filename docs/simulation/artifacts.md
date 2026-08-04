# Simulation Artifacts

Runs publish under `backend/artifacts/simulation/runs/<run-id>/`. A run ID is the first 20 hexadecimal characters of the canonical simulation-run-config SHA-256. The run contract includes simulator version; strategy, market, path-config, and path hashes; selected policy parameters; separate option and futures cost configurations; runtime kill-switch state; accounting tolerance; and quantity-rounding convention. It is deterministic and contains no wall-clock value or artifact path.

The store writes a running manifest and all artifacts to `.tmp-<run-id>`, then atomically renames the directory. Existing runs are immutable. Writer failures publish a failed manifest. Temporary directories are not listed as completed runs.

Each completed run contains `manifest.json`, `strategy-config.json`, `market-config.json`, `run-config.json`, `path-config.json`, `path.csv`, `market-states.csv`, `option-valuations.csv`, `hedge-decisions.csv`, `risk-decisions.csv`, `order-intents.csv`, `fills.csv`, `ledger.csv`, `positions.csv`, `pnl-attribution.csv`, and `summary.json`.

The manifest records strategy, market, path config, path, policy config, option cost, futures cost, runtime risk, and run-config hashes. It also records the complete clock config, selected expiry and strike, both multipliers, futures delta per contract, accounting tolerance, rounding convention, source commit, runtime timestamps, and artifact location. Failed runs retain this specification. Decision and risk CSVs include session date, local and UTC timestamps, timed delta fields, quantities and counts, and position/session P&L. Generated run directories are ignored and are never source artifacts.
