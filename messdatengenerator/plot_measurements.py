"""Alle NPY-Messungen eines Ordners in einer gemeinsamen Abbildung anzeigen."""

import argparse
import json
from pathlib import Path

import numpy as np


def load_measurements(folder):
    files = sorted(p for p in folder.glob("*.npy") if not p.stem.endswith("_labels"))
    if not files:
        raise ValueError(f"Keine NPY-Messdateien gefunden: {folder}")
    measurements = []
    for path in files:
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        rate = float(metadata["sample_rate_hz"])
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError(f"Ungültige Abtastrate: {path.name}")
        values = np.load(path, mmap_mode="r", allow_pickle=False)
        if values.ndim != 2 or values.shape[1] != 3 or len(values) == 0:
            raise ValueError(f"Erwartet werden drei Spalten X/Y/Z: {path.name}")
        if not np.isfinite(values).all():
            raise ValueError(f"Nicht endliche Messwerte: {path.name}")
        measurements.append((path.stem, rate, values))
    return measurements


def display_points(values, rate, axis, start, end, bins=1200):
    """Minima/Maxima zeitlich geordnet erhalten, statt Spitzen zu überspringen."""
    first = max(0, int(np.floor(start * rate)))
    last = min(len(values), int(np.ceil(end * rate)) + 1)
    if last <= first:
        return np.array([]), np.array([])
    if last - first <= 2 * bins:
        indices = np.arange(first, last)
    else:
        edges = np.linspace(first, last, bins + 1, dtype=int)
        selected = []
        for left, right in zip(edges[:-1], edges[1:]):
            segment = values[left:right, axis]
            selected.extend(sorted((left + int(np.argmin(segment)),
                                    left + int(np.argmax(segment)))))
        indices = np.asarray(selected)
    return indices / rate, values[indices, axis]


def make_figure(measurements, start=0.0, end=None):
    import matplotlib.pyplot as plt

    maximum = max((len(data) - 1) / rate for _, rate, data in measurements)
    if end is None:
        end = maximum
    if not (np.isfinite(start) and np.isfinite(end) and 0 <= start < end and start < maximum):
        raise ValueError("Zeitbereich muss endlich sein und Messdaten enthalten: 0 <= start < end.")
    end = min(end, maximum)
    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle("Synthetische Schwingungsmessungen – Vergleich", fontsize=17, fontweight="bold")
    colors = plt.get_cmap("tab10")
    lines = []
    for index, (name, rate, data) in enumerate(measurements):
        for axis, panel in enumerate(axes):
            x, y = display_points(data, rate, axis, start, end)
            line, = panel.plot(x, y, color=colors(index % 10), linewidth=0.65,
                               alpha=0.8, label=name)
            lines.append((line, data, rate, axis))
    for label, panel in zip("XYZ", axes):
        panel.set_ylabel(f"{label} · Beschleunigung [m/s²]")
        panel.grid(True, alpha=0.22)
        panel.set_xlim(start, end)
    axes[-1].set_xlabel("Zeit seit Messbeginn [s]")
    handles, labels = axes[0].get_legend_handles_labels()
    columns = min(4, len(handles))
    legend_rows = (len(handles) + columns - 1) // columns
    legend_height = 0.035 * legend_rows
    fig.set_size_inches(14, 9 + max(0, legend_rows - 1) * 0.3)
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.95),
               ncol=columns, frameon=False, fontsize=9)
    fig.text(0.5, 0.015,
             "Übersicht: Min-/Max-Werte pro Zeitabschnitt. Beim Zoomen werden Details neu geladen.\n"
             "Alle Dateien sind auf ihren Messbeginn ausgerichtet; keine realen Sensormessungen.",
             ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, 0.065, 1, 0.94 - legend_height))

    def refresh(panel):
        left, right = sorted(panel.get_xlim())
        for line, data, rate, axis in lines:
            line.set_data(*display_points(data, rate, axis, left, right))
        fig.canvas.draw_idle()

    for panel in axes:
        panel.callbacks.connect("xlim_changed", refresh)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path,
                        default=Path(__file__).resolve().parent / "beispieldaten")
    parser.add_argument("--output", type=Path, help="PNG-Ausgabe; Standard: messungen_uebersicht.png im Datenordner")
    parser.add_argument("--start", type=float, default=0, help="Beginn des dargestellten Bereichs in Sekunden")
    parser.add_argument("--end", type=float, help="Ende des dargestellten Bereichs in Sekunden")
    parser.add_argument("--no-show", action="store_true", help="Nur PNG speichern, kein Fenster öffnen")
    args = parser.parse_args()
    if args.no_show:
        import matplotlib
        matplotlib.use("Agg")
    try:
        measurements = load_measurements(args.folder)
        fig = make_figure(measurements, args.start, args.end)
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
    output = args.output or args.folder / "messungen_uebersicht.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    print(f"{len(measurements)} Messungen dargestellt. Diagramm: {output.resolve()}")
    import matplotlib.pyplot as plt
    if not args.no_show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
