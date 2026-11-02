"""Gemeinsame Merkmalsberechnung und Inferenz für lokale Tests und die Cloud."""

import json
from pathlib import Path

import numpy as np


FEATURE_NAMES = [f"{kind}_{axis}" for kind in ("rms", "peak", "crest") for axis in "xyz"]


def extract_features(signal, sample_rate, window_seconds):
    """Aus jedem nicht überlappenden Abschnitt neun Merkmale berechnen."""
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 2 or signal.shape[1] != 3 or not np.isfinite(signal).all():
        raise ValueError("Messdaten müssen endlich sein und drei Achsen enthalten.")
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("Die Abtastrate muss positiv sein.")
    if not np.isfinite(window_seconds) or window_seconds <= 0:
        raise ValueError("Die Abschnittslänge muss positiv sein.")
    exact_size = sample_rate * window_seconds
    size = round(exact_size)
    if size < 2 or not np.isclose(size, exact_size, rtol=0, atol=1e-8):
        raise ValueError("Ein Abschnitt muss eine ganze Anzahl von mindestens zwei Werten enthalten.")
    if len(signal) == 0 or len(signal) % size:
        # Keine Messwerte unbemerkt abschneiden. Bei Streaming muss der Aufrufer
        # unvollständige Abschnitte bis zum nächsten Datenpaket aufbewahren.
        raise ValueError("Die Messung muss aus vollständigen Abschnitten bestehen.")
    windows = signal.reshape(-1, size, 3)
    rms = np.sqrt(np.mean(windows ** 2, axis=1))  # Effektivwert: Schwingungsenergie
    peak = np.max(np.abs(windows), axis=1)       # Größter Ausschlag pro Achse
    # Crest-Faktor: Verhältnis von Spitze zu Effektivwert, empfindlich für Impulse.
    crest = np.divide(peak, rms, out=np.zeros_like(peak), where=rms > 0)
    return np.concatenate([rms, peak, crest], axis=1)


def read_measurement(path):
    """Rohdaten und technische Metadaten laden; Labels sind keine Modelleingabe."""
    path = Path(path)
    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    signal = np.load(path, allow_pickle=False)
    if meta.get("axes") != ["x", "y", "z"] or meta.get("unit") != "m/s^2":
        raise ValueError(f"Unpassende Achsen oder Einheit: {path}")
    if meta.get("sample_count") != len(signal):
        raise ValueError(f"Messwertzahl und Metadaten stimmen nicht überein: {path}")
    return signal, meta


def load_model(path):
    # NPZ enthält nur Zahlen und JSON, keine ausführbaren Pickle-Objekte.
    with np.load(path, allow_pickle=False) as archive:
        model = {key: archive[key].copy() for key in archive.files}
    model["config"] = json.loads(str(model["config"]))
    if model["config"]["feature_names"] != FEATURE_NAMES:
        raise ValueError("Unbekannte Merkmalsreihenfolge.")
    return model


def reconstruction_errors(features, model):
    # Exakt dieselbe Normalisierung wie im Training verwenden. Neue Messungen
    # dürfen keinen eigenen Mittelwert erhalten: Dies könnte Anomalien verdecken.
    normalized = (features - model["mean"]) / model["scale"]
    reconstructed = normalized
    for layer in range(model["config"]["layer_count"]):
        reconstructed = reconstructed @ model[f"weight_{layer}"] + model[f"bias_{layer}"]
        if layer < model["config"]["layer_count"] - 1:
            reconstructed = np.tanh(reconstructed)
    # Die Ausgabeschicht bleibt linear, damit auch negative standardisierte
    # Merkmalswerte rekonstruiert werden können. Fehler: Mittel über neun Merkmale.
    return np.mean((normalized - reconstructed) ** 2, axis=1)


def analyze(path, model):
    signal, meta = read_measurement(path)
    config = model["config"]
    if meta["sample_rate_hz"] != config["sample_rate_hz"]:
        raise ValueError("Abtastrate stimmt nicht mit dem Modell überein.")
    features = extract_features(signal, meta["sample_rate_hz"], config["window_seconds"])
    errors = reconstruction_errors(features, model)
    fraction = float(np.mean(errors > config["threshold"]))
    return {
        "file": Path(path).name,
        "window_count": len(errors),
        "anomalous_windows": int(np.sum(errors > config["threshold"])),
        "anomalous_fraction": fraction,
        "measurement_anomalous": fraction >= config["alarm_fraction"],
        "mean_error": float(np.mean(errors)),
        "max_error": float(np.max(errors)),
    }, errors
