import os
import subprocess
import sys

from app.market_data.normalization.serialization import canonical_normalization_json


def test_canonical_set_serialization_is_sorted() -> None:
    assert canonical_normalization_json({"values": {"gamma", "alpha", "beta"}}) == '{"values":["alpha","beta","gamma"]}'


def test_canonical_serialization_matches_across_hash_seeds() -> None:
    code = (
        "from app.market_data.normalization.serialization import canonical_normalization_json;"
        "print(canonical_normalization_json({'values': {'gamma', 'alpha', 'beta'}}))"
    )
    outputs = []
    for seed in ("1", "999"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        outputs.append(
            subprocess.run(
                [sys.executable, "-c", code],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout
        )
    assert outputs[0] == outputs[1]
