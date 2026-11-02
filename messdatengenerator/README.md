# Zwei synthetische Messungen für den Cloud-Funktionstest

Der Generator erzeugt genau eine gute und eine schlechte Messung. Beide dauern 60 Sekunden mit 10.000 Messwerten pro Sekunde je Achse (X, Y, Z). Die Daten dienen zum Testen der Cloud-Verarbeitung, nicht zur Bewertung einer realen Fehlerdiagnose oder als ausreichender Trainingsdatensatz für einen Autoencoder.

## Dateien

| Datei | Inhalt |
|---|---|
| `messung_gut.npy` | Normale Schwingung mit Harmonischen und geringem Messrauschen |
| `messung_schlecht.npy` | Dasselbe Grundsignal mit fünf gedämpften Störimpulsen pro Sekunde über die gesamten 60 Sekunden |
| `*_labels.npy` | Gute Messung durchgehend 0, schlechter Betriebszustand durchgehend 1 |
| `*.json` | Abtastrate, Einheiten, Seed, Simulationsparameter und Statistik |

Jede Signaldatei enthält 600.000 Zeilen und drei Spalten in float32, somit 7,2 MB Nutzdaten. Einheit: m/s², ohne Erdbeschleunigung. Die Impulse schwingen bei 1.200 Hz aus und wirken unterschiedlich stark auf die Achsen. Zwischen einzelnen Impulsen klingt die Störung ab; der schlechte Betriebszustand besteht dennoch über das gesamte Messfenster. Frequenzen und Amplituden sind Simulationsannahmen. Labels dürfen nicht als Modelleingabe verwendet werden.

## Neue Messungen erzeugen

Aus dem Projekt-Hauptordner:

```powershell
python -m pip install -r messdatengenerator/requirements.txt
python messdatengenerator/generate_measurements.py --output messdatengenerator/daten_neu
```

`--seed 123` erzeugt eine andere reproduzierbare Realisierung, `--severity 0.5` reduziert die Impulsstärke, `--csv` schreibt zusätzlich CSV-Dateien. Gleiche Parameter und NumPy-Version ergeben gleiche Daten. Nicht leere Zielordner werden nicht überschrieben.

## Alle Messungen anzeigen

```powershell
python messdatengenerator/plot_measurements.py
```

Die Standardansicht lädt alle Messdateien aus `beispieldaten` neben dem Skript samt JSON-Metadaten. Label-Dateien werden ausgelassen. Drei Teilplots zeigen X/Y/Z; zusätzlich wird `messungen_uebersicht.png` gespeichert und bei erneutem Aufruf ersetzt. Messdateien bleiben unverändert.

Über die Lupe einen Zeitbereich vergrößern. Die Übersicht erhält Minima und Maxima pro Zeitabschnitt; beim Zoomen werden feinere Messpunkte nachgeladen. Die verdichtete Gesamtansicht ist nicht zur Frequenzanalyse geeignet. Vergrößerte Ansichten über das Speichern-Symbol exportieren.

```powershell
python messdatengenerator/plot_measurements.py --no-show
python messdatengenerator/plot_measurements.py --start 30 --end 30.1 --output messdatengenerator/detail.png
python messdatengenerator/plot_measurements.py --folder messdatengenerator/daten_neu
```

## In Python einlesen

```python
import numpy as np
daten = np.load("messdatengenerator/beispieldaten/messung_gut.npy", allow_pickle=False)
zeit = np.arange(len(daten)) / 10000
print(daten.shape)  # (600000, 3)
```

Frühere Beispielszenarien sind in dieser bereinigten Abgabe nicht enthalten. Alle Skripte arbeiten lokal; es werden keine Azure-Ressourcen angelegt.
