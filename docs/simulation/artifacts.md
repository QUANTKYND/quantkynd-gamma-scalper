# Simulation Artifacts

Runs publish under `backend/artifacts/simulation/runs/<run-id>/`. A run ID is the first 20 hexadecimal characters of SHA-256 over simulator version, strategy hash, path hash, policy, and both cost configurations. It is deterministic and contains no timestamp.

The store writes a running manifest and all artifacts to `.tmp-<run-id>`, then atomically renames the directory. Existing runs are immutable. Writer failures publish a failed manifest. Temporary directories are not listed as completed runs.

Each completed run contains `manifest.json`, `strategy-config.json`, `path-config.json`, `path.csv`, `market-states.csv`, `option-valuations.csv`, `hedge-decisions.csv`, `risk-decisions.csv`, `order-intents.csv`, `fills.csv`, `ledger.csv`, `positions.csv`, `pnl-attribution.csv`, and `summary.json`.

Runtime timestamps, artifact location, and source commit appear in the manifest. Strategy, path configuration, market scenario, policy parameters, and cost model have explicit provenance hashes. Generated run directories are ignored and are never source artifacts.
