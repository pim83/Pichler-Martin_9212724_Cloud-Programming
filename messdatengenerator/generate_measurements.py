"""Synthetische dreiachsige Schwingungsdaten; keine reale Fehlerdiagnose.

Aufruf: python generate_measurements.py --output daten
Benötigt NumPy. NPY-Dateien enthalten float32, Form (Messwerte, 3).
"""

import argparse
import json
from pathlib import Path

import numpy as np


def normal_signal(sample_rate, duration, rng):
    """Periodische Anregung, Harmonische und geringes Messrauschen."""
    count = round(sample_rate * duration)
    t = np.arange(count, dtype=np.float64) / sample_rate
    # Variationen verhindern, dass alle normalen Messfenster identisch sind.
    base_hz = float(rng.uniform(28, 32))
    amplitudes = np.array([0.45, 0.30, 0.20]) * rng.uniform(0.9, 1.1, 3)
    phases = rng.uniform(0, 2 * np.pi, 3)
    envelope = 1 + 0.15 * np.sin(2 * np.pi * 0.5 * t)
    signal = np.empty((count, 3), dtype=np.float32)
    for axis in range(3):
        wave = (
            np.sin(2 * np.pi * base_hz * t + phases[axis])
            + 0.25 * np.sin(2 * np.pi * 2 * base_hz * t + phases[axis])
            + 0.12 * np.sin(2 * np.pi * 5 * base_hz * t + phases[axis])
        )
        signal[:, axis] = (
            amplitudes[axis] * envelope * wave + rng.normal(0, 0.025, count)
        )
    return signal, {"base_frequency_hz": base_hz,
                    "amplitude_per_axis_m_s2": amplitudes.tolist(),
                    "noise_std_m_s2": 0.025}


def disturb(signal, sample_rate, severity, rng):
    """Wiederkehrende Impulse über das gesamte Messfenster."""
    result = signal.copy()
    count = len(signal)
    weights = np.array([1.0, 0.6, 0.3])
    pulse_length = round(0.05 * sample_rate)
    pulse_t = np.arange(pulse_length) / sample_rate
    pulse = np.exp(-pulse_t / 0.008) * np.sin(2 * np.pi * 1200 * pulse_t)
    for start in range(0, count, round(0.2 * sample_rate)):
        end = min(start + pulse_length, count)
        magnitude = severity * rng.uniform(1.5, 2.5)
        result[start:end] += (
            magnitude * pulse[:end-start, None] * weights
        ).astype(np.float32)
    # Label beschreibt den gestörten Betriebszustand, auch zwischen Impulsen.
    mask = np.ones(count, dtype=np.uint8)
    return result, mask, {
        "start_sample": 0, "end_sample_exclusive": count,
        "start_seconds": 0, "end_seconds": count / sample_rate,
        "type": "repeated_impacts",
        "label_semantics": "faulty operating condition throughout the window",
        "parameters": {"severity": severity, "axis_weights": weights.tolist(),
                       "resonance_hz": 1200, "repetition_hz": 5,
                       "decay_seconds": 0.008}
    }


def save_record(output, stem, signal, mask, metadata, csv=False):
    np.save(output / f"{stem}.npy", signal, allow_pickle=False)
    np.save(output / f"{stem}_labels.npy", mask, allow_pickle=False)
    metadata["statistics"] = {
        "rms_per_axis_m_s2": np.sqrt(np.mean(signal.astype(np.float64)**2, axis=0)).tolist(),
        "peak_abs_per_axis_m_s2": np.max(np.abs(signal), axis=0).tolist(),
    }
    (output / f"{stem}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    if csv:
        # Nur optional: Text benötigt erheblich mehr Platz als float32-Binärdaten.
        with (output / f"{stem}.csv").open("w", encoding="utf-8", newline="") as stream:
            stream.write("time_s,accel_x_m_s2,accel_y_m_s2,accel_z_m_s2,label\n")
            for i, row in enumerate(signal):
                stream.write(f"{i/metadata['sample_rate_hz']:.8f},"
                             f"{row[0]:.8g},{row[1]:.8g},{row[2]:.8g},{mask[i]}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("daten"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--severity", type=float, default=1.0)
    parser.add_argument("--csv", action="store_true", help="Zusätzlich CSV-Dateien schreiben")
    args = parser.parse_args()
    if args.seed < 0:
        parser.error("seed muss nicht negativ sein.")
    if not np.isfinite(args.severity) or not 0 < args.severity <= 10:
        parser.error("severity muss größer als 0 und höchstens 10 sein.")
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error("Zielordner ist nicht leer oder keine Ordneradresse. Neuen Ordner wählen.")
    args.output.mkdir(parents=True, exist_ok=True)
    sample_rate, duration = 10000, 60
    rng = np.random.default_rng(np.random.SeedSequence([args.seed, 0]))
    signal, normal_parameters = normal_signal(sample_rate, duration, rng)
    base = {
        "generator_version": "2.0", "synthetic": True,
        "seed": args.seed, "pair_id": "pair_0000",
        "test_stand_id": "SIM-01", "test_id": "SIM-TEST-0000",
        "sample_rate_hz": sample_rate, "duration_seconds": duration,
        "sample_count": len(signal), "axes": ["x", "y", "z"],
        "unit": "m/s^2", "dtype": "float32", "gravity_included": False,
        "time_reference": "seconds since measurement start; t[i] = i / sample_rate_hz",
        "normal_parameters": normal_parameters,
    }
    save_record(args.output, "messung_gut", signal, np.zeros(len(signal), dtype=np.uint8),
                {**base, "condition": "normal", "disturbance": None}, args.csv)
    fault_rng = np.random.default_rng(np.random.SeedSequence([args.seed, 0, 2]))
    disturbed, labels, event = disturb(signal, sample_rate, args.severity, fault_rng)
    save_record(args.output, "messung_schlecht", disturbed, labels,
                {**base, "condition": "impacts", "disturbance": event}, args.csv)
    print(f"Fertig: gute und schlechte Messung (je 60 s, 10 kHz, 3 Achsen) in {args.output.resolve()}")


if __name__ == "__main__":
    main()
