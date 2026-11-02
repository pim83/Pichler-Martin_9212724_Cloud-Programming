"""Kleinen Autoencoder lokal trainieren, kalibrieren und als NPZ exportieren.

Aufruf im Projektordner: python autoencoder/train.py
"""

import argparse
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from model import FEATURE_NAMES, extract_features, load_model, read_measurement, reconstruction_errors


ROOT = Path(__file__).resolve().parents[1]


def load_split(folder, window_seconds, expected_split):
    matrices, sources = [], []
    files = sorted(folder.glob("*.npy"))
    if not files:
        raise ValueError(f"Keine Messungen gefunden: {folder}")
    for path in files:
        signal, meta = read_measurement(path)
        if meta.get("condition") != "normal" or meta.get("split") != expected_split:
            raise ValueError(f"Falsche Datenzuordnung: {path}")
        if meta["sample_rate_hz"] != 10000:
            raise ValueError("Dieses Modell erwartet Messungen mit 10 kHz.")
        matrices.append(extract_features(signal, 10000, window_seconds))
        sources.append({
            "file": f"{expected_split}/{path.name}", "seed": meta["seed"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return np.concatenate(matrices), sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "trainingsdaten")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "modell_v2")
    parser.add_argument("--window-seconds", type=float, default=0.1)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Ausgabeordner existiert bereits. Für einen neuen Lauf --output angeben.")

    # 1. Ganze Messungen sind bereits getrennt. Niemals zufällig Abschnitte
    # derselben Messung auf Training und Validierung verteilen (Datenleck).
    training, training_sources = load_split(args.data / "training", args.window_seconds, "training")
    validation, validation_sources = load_split(args.data / "validierung", args.window_seconds, "validierung")
    for key in ("seed", "sha256"):
        if {s[key] for s in training_sources} & {s[key] for s in validation_sources}:
            raise ValueError("Training und Validierung enthalten überlappende Messungen.")

    # 2. Unterschiedliche Größenordnungen ausgleichen. Mittelwert und Streuung
    # ausschließlich am Training lernen; die Validierung wird nur transformiert.
    scaler = StandardScaler().fit(training)
    normalized = scaler.transform(training)

    # 3. Ein Autoencoder lernt Eingabe -> Eingabe, keine Gut/Schlecht-Labels.
    # Aufbau: 9 -> 6 -> 3 -> 6 -> 9. Der Engpass mit drei Neuronen zwingt
    # das Netz zu einer kompakten Darstellung des normalen Schwingungsverhaltens.
    # MLPRegressor liefert die lineare Ausgabeschicht für die Rekonstruktion.
    # Keine interne zufällige Validierungsaufteilung; unsere fünf separaten
    # Messungen bleiben vollständig für die anschließende Kalibrierung reserviert.
    network = MLPRegressor(
        hidden_layer_sizes=(6, 3, 6), activation="tanh", solver="adam",
        batch_size=256, learning_rate_init=0.001, max_iter=2000,
        tol=1e-5, n_iter_no_change=20, early_stopping=False, random_state=2026,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        network.fit(normalized, normalized)
    training_warnings = [str(w.message) for w in caught]

    # 4. Der Fehler ist die mittlere quadratische Abweichung der neun
    # standardisierten Merkmale. Das 99. Perzentil normaler Validierungsfehler
    # bestimmt die Abschnittsschwelle. Es garantiert keine reale Fehlalarmrate.
    valid_normalized = scaler.transform(validation)
    valid_errors = np.mean((valid_normalized - network.predict(valid_normalized)) ** 2, axis=1)
    threshold = float(np.quantile(valid_errors, 0.99))
    config = {
        "model_version": "1.0", "feature_names": FEATURE_NAMES,
        "architecture": [9, 6, 3, 6, 9], "activation": "tanh",
        "layer_count": len(network.coefs_), "sample_rate_hz": 10000,
        "window_seconds": args.window_seconds, "threshold": threshold,
        "threshold_quantile": 0.99,
        # Vor dem Test festgelegte Prototyp-Regel: Eine Messung ist auffällig,
        # wenn mindestens 10 % ihrer Abschnitte die Fehlerschwelle überschreiten.
        # Diese fachliche Alarmregel ist noch nicht an realen Daten validiert.
        "alarm_fraction": 0.10, "random_seed": 2026,
        "numpy_version": np.__version__, "sklearn_version": sklearn.__version__,
    }

    # 5. Gewichte, Normalisierung und Konfiguration gemeinsam speichern.
    # Für die spätere Inferenz reicht NumPy; scikit-learn wird nur zum Trainieren
    # benötigt. Das Modell enthält keine Rohdaten und keine Test-Labels.
    arrays = {"mean": scaler.mean_, "scale": scaler.scale_, "config": np.array(json.dumps(config))}
    for index, (weight, bias) in enumerate(zip(network.coefs_, network.intercepts_)):
        arrays[f"weight_{index}"] = weight
        arrays[f"bias_{index}"] = bias
    args.output.mkdir(parents=True)
    model_path = args.output / "autoencoder.npz"
    np.savez_compressed(model_path, **arrays)

    # Den tatsächlich gespeicherten Export laden und mit scikit-learn vergleichen.
    # Dies prüft, dass die spätere Cloud-Berechnung denselben Fehler liefert.
    exported = load_model(model_path)
    np.testing.assert_allclose(reconstruction_errors(validation, exported), valid_errors, rtol=1e-10, atol=1e-12)
    report = {
        "config": config, "training_windows": len(training),
        "validation_windows": len(validation), "epochs": network.n_iter_,
        "training_loss_final": network.loss_, "loss_curve": network.loss_curve_,
        "training_warnings": training_warnings,
        "validation_fraction_above_threshold": float(np.mean(valid_errors > threshold)),
        "export_verified": True,
        "training_sources": training_sources, "validation_sources": validation_sources,
    }
    (args.output / "training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    print(f"Trainiert: {len(training)} Abschnitte; {network.n_iter_} Epochen; Schwelle {threshold:.6f}")
    print(f"Modell gespeichert und Export geprüft: {model_path}")
    for warning in training_warnings:
        print(f"Trainingshinweis: {warning}")


if __name__ == "__main__":
    main()
