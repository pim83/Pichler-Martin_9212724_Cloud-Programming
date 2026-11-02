"""Separate normale Trainings- und Validierungsmessungen erzeugen."""

import argparse
import json
from pathlib import Path

import numpy as np

from generate_measurements import normal_signal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "trainingsdaten",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    targets = [output / name for name in ("training", "validierung", "manifest.json")]
    if any(path.exists() for path in targets):
        parser.error("Trainingsdaten existieren bereits. Einen neuen Ausgabeordner wählen.")
    if output.exists() and not output.is_dir():
        parser.error("Ausgabeziel ist kein Ordner.")

    sample_rate, duration = 10000, 60
    records = []
    # Eigene Seeds; Seed 42 der vorhandenen Funktionstests bleibt ausgeschlossen.
    splits = {"training": range(1000, 1020), "validierung": range(2000, 2005)}
    for split, seeds in splits.items():
        folder = output / split
        folder.mkdir(parents=True)
        for index, seed in enumerate(seeds, start=1):
            rng = np.random.default_rng(np.random.SeedSequence([seed, 0]))
            signal, parameters = normal_signal(sample_rate, duration, rng)
            stem = f"normal_{index:03d}"
            metadata = {
                "dataset_version": "1.0",
                "generator": "generate_measurements.normal_signal",
                "numpy_version": np.__version__,
                "synthetic": True,
                "condition": "normal",
                "split": split,
                "seed": seed,
                "seed_sequence_entropy": [seed, 0],
                "sample_rate_hz": sample_rate,
                "duration_seconds": duration,
                "sample_count": len(signal),
                "axes": ["x", "y", "z"],
                "unit": "m/s^2",
                "dtype": "float32",
                "gravity_included": False,
                "normal_parameters": parameters,
            }
            np.save(folder / f"{stem}.npy", signal, allow_pickle=False)
            (folder / f"{stem}.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            records.append({"file": f"{split}/{stem}.npy", "seed": seed, "split": split})

    manifest = {
        "dataset_version": "1.0",
        "numpy_version": np.__version__,
        "training_count": 20,
        "validation_count": 5,
        "windowing": "Full recordings; configurable windowing during training, initially 0.1 s.",
        "records": records,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Fertig: 20 Trainings- und 5 Validierungsmessungen in {output}")


if __name__ == "__main__":
    main()
