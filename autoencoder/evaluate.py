"""Gespeichertes Modell auf die reservierten Beispielmessungen anwenden."""

import argparse
import json
from pathlib import Path

from model import analyze, load_model


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=root / "autoencoder/modell_v2/autoencoder.npz")
    parser.add_argument("--examples", type=Path, default=root / "messdatengenerator/beispieldaten")
    args = parser.parse_args()
    model = load_model(args.model)
    results = []
    # Erwartete Zustände dienen ausschließlich der Ergebnisprüfung. Die Funktion
    # analyze() erhält weder diese Erwartungen noch die vorhandenen Label-Dateien.
    for name, expected in [("messung_gut.npy", False), ("messung_schlecht.npy", True)]:
        result, _ = analyze(args.examples / name, model)
        result["expected_anomalous"] = expected
        result["matches_expectation"] = result["measurement_anomalous"] == expected
        results.append(result)
        print(f"{name}: {result['anomalous_windows']}/{result['window_count']} Abschnitte auffällig "
              f"({result['anomalous_fraction']:.1%}); Messung auffällig: {result['measurement_anomalous']}")
    # Ergebnisbericht darf beim erneuten Prüfen aktualisiert werden; Modell und
    # Schwellenwert werden hier niemals verändert oder anhand der Tests angepasst.
    report = {
        "threshold": model["config"]["threshold"],
        "alarm_fraction": model["config"]["alarm_fraction"], "results": results,
        "limitation": "Zwei synthetische Funktionstests, kein Nachweis realer Diagnosequalität.",
    }
    (args.model.parent / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
