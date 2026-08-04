"""Persist a close-to-close volatility research run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from app.core.config import settings
from app.schemas.rv import RVRunManifest
from app.services.rv_run_store import RVRunStore, current_git_commit, stable_config_hash
from app.services.rv_service import (
    DEFAULT_ARTIFACT_ROOT,
    DEFAULT_CSV_PATH,
    REPO_ROOT,
    build_research_snapshot,
    feature_artifact_frame,
    history_artifact_frame,
)


def _date_arg(value: str) -> date:
    return date.fromisoformat(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--model", choices=("naive", "ewma"), default="ewma")
    parser.add_argument("--horizon-sessions", type=int, default=5)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic prices")
    parser.add_argument("--seed", type=int, default=settings.rv_synthetic_seed)
    parser.add_argument("--periods", type=int, default=settings.rv_synthetic_periods)
    parser.add_argument("--end-date", type=_date_arg, default=settings.rv_synthetic_end_date)
    parser.add_argument("--initial-price", type=float, default=settings.rv_synthetic_initial_price)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    created_at = datetime.now(UTC)
    try:
        snapshot = build_research_snapshot(
            symbol=args.symbol,
            csv_path=args.csv_path,
            force_synthetic=args.synthetic,
            synthetic_seed=args.seed,
            synthetic_periods=args.periods,
            synthetic_end_date=args.end_date,
            synthetic_initial_price=args.initial_price,
            horizon_sessions=args.horizon_sessions,
        )
        model_result = snapshot.backtest["models"][args.model]
        summary = _summary_for_artifact(snapshot, args.model)
        config = {
            "symbol": snapshot.symbol,
            "dataset_id": snapshot.dataset_metadata.dataset_id,
            "estimator_id": snapshot.estimator_metadata.estimator_id,
            "model": args.model,
            "model_parameters": model_result["model_parameters"],
            "horizon_sessions": args.horizon_sessions,
            "evaluation_method": snapshot.backtest["evaluation_method"],
        }
        config_hash = stable_config_hash(config)
        run_id = _run_id(created_at, args.model, config_hash)
        final_dir = args.artifact_root / "runs" / run_id
        manifest = RVRunManifest(
            run_id=run_id,
            created_at=created_at,
            completed_at=None,
            status="running",
            symbol=snapshot.symbol,
            dataset_id=snapshot.dataset_metadata.dataset_id,
            estimator_id=snapshot.estimator_metadata.estimator_id,
            model=args.model,
            model_parameters=model_result["model_parameters"],
            horizon_sessions=args.horizon_sessions,
            evaluation_method=snapshot.backtest["evaluation_method"],
            config_hash=config_hash,
            git_commit=current_git_commit(REPO_ROOT),
            artifact_directory=str(final_dir),
            failure_reason=None,
        )

        store = RVRunStore(args.artifact_root)

        def write_artifacts(run_dir: Path) -> None:
            (run_dir / "summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n"
            )
            history_artifact_frame(snapshot, args.model).to_csv(
                run_dir / "forecast-history.csv",
                index=False,
            )
            feature_artifact_frame(snapshot).to_csv(run_dir / "features.csv", index_label="date")

        completed = store.create_run(base_manifest=manifest, write_artifacts=write_artifacts)
        if completed.status == "failed":
            print(completed.failure_reason or "RV research run failed", file=sys.stderr)
            return 1
        print(completed.model_dump_json())
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _summary_for_artifact(snapshot, model: str) -> dict:
    result = snapshot.backtest["models"][model]
    rows = result["metric_rows"]
    return {
        "symbol": snapshot.symbol,
        "model": model,
        "model_parameters": result["model_parameters"],
        "horizon_sessions": snapshot.backtest["horizon_sessions"],
        "evaluation_method": snapshot.backtest["evaluation_method"],
        "chart_stride": snapshot.backtest["chart_stride"],
        "metric_stride": snapshot.backtest["metric_stride"],
        "overlapping_chart_targets": snapshot.backtest["overlapping_chart_targets"],
        "overlapping_metric_targets": snapshot.backtest["overlapping_metric_targets"],
        "evaluation_start": rows.index[0].date().isoformat() if not rows.empty else None,
        "evaluation_end": rows.index[-1].date().isoformat() if not rows.empty else None,
        "estimator": snapshot.estimator_metadata.model_dump(mode="json"),
        "dataset": snapshot.dataset_metadata.model_dump(mode="json"),
        "variance_metrics": result["variance_metrics"],
        "volatility_metrics": result["volatility_metrics"],
        "regime_metrics": result["regime_metrics"],
    }


def _run_id(created_at: datetime, model: str, config_hash: str) -> str:
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    return f"rv-{timestamp}-{model}-{config_hash[-8:]}"


if __name__ == "__main__":
    raise SystemExit(main())
