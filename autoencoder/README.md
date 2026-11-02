# Kleiner Autoencoder für die Schwingungsanalyse

Das lokal trainierte Modell rekonstruiert neun Merkmale normaler Schwingungen.
Eine große Abweichung zwischen Eingabe und Rekonstruktion gilt als Auffälligkeit.
Die wichtigen Schritte sind im Python-Code auf Deutsch kommentiert.

## Einstieg in den Code

1. `model.py`: Messungen einlesen, Merkmale berechnen und gespeichertes Modell anwenden.
2. `train.py`: Daten trennen, normalisieren, Netz trainieren, Schwelle bestimmen und exportieren.
3. `evaluate.py`: Gespeichertes Modell mit der guten und schlechten Beispielmessung prüfen.
4. `test_model.py`: Fachliche Prüfungen der Merkmalsberechnung und Eingabevalidierung.

## Verfahren

- 20 vollständige normale Messungen werden zum Training verwendet, fünf weitere
  normale Messungen ausschließlich zur Kalibrierung des Schwellenwerts.
- Die Abschnittslänge ist einstellbar, standardmäßig 0,1 Sekunden. Die Rohdateien
  bleiben unverändert. Daraus entstehen 12000 Trainings- und 3000 Validierungsabschnitte.
- Pro Abschnitt werden Effektivwert (RMS), absoluter Spitzenwert und Crest-Faktor
  je Achse berechnet. Reihenfolge: RMS X/Y/Z, Spitze X/Y/Z, Crest-Faktor X/Y/Z.
- Standardisierung: Mittelwert abziehen und durch Standardabweichung teilen.
  Beide Größen werden ausschließlich aus den Trainingsmerkmalen gelernt.
- Netz: **9 → 6 → 3 → 6 → 9**, tanh in den verdeckten Schichten, lineare Ausgabe.
  Die drei mittleren Neuronen bilden den Engpass. Trainiert wird mit Adam.
  Eingabe und Trainingsziel sind dieselben normalisierten Merkmale: Dadurch
  wird der MLPRegressor als Autoencoder verwendet, ohne Gut/Schlecht-Labels.
- Maximal 2000 Epochen; Abbruch bei ausbleibender ausreichender Verbesserung des
  Trainingsverlusts (`tol=1e-5`, `n_iter_no_change=20`). Der Zufallsstart ist 2026.
  Es erfolgt keine interne zufällige Aufteilung in Trainings- und Validierungsfenster.
- Der Rekonstruktionsfehler ist die mittlere quadratische Abweichung über die
  neun standardisierten Merkmale. Die Schwelle entspricht dem 99. Perzentil
  der normalen Validierungsfehler. Ein Abschnitt ist auffällig bei Fehler > Schwelle.
- **Alarmregel für den Prototyp:** Eine Messung ist auffällig, wenn mindestens
  10 % ihrer Abschnitte auffällig sind. Diese Regel wurde vor Auswertung der
  Beispielmessungen festgelegt; sie ist keine an realen Daten validierte Grenze.

## Gespeichertes Modell und Ergebnis

**Der abgeschlossene Trainingslauf liegt in `modell_v2/`.** Der erste Lauf in
`modell_v1/` erreichte nach 500 Epochen sein Limit mit einer Konvergenzwarnung
ist in dieser bereinigten Abgabe nicht enthalten. Danach wurde nur das
Epochenlimit erhöht; die Testmessungen wurden erst mit dem abgeschlossenen Lauf geprüft.

Der zweite Lauf endete nach **1658 Epochen**, ohne Konvergenzwarnung.
Die Abschnittsschwelle beträgt **1,0965192193** (dimensionsloser Fehler nach Standardisierung).

| Funktionstest | Auffällige Abschnitte | Anteil | Messung auffällig |
|---|---:|---:|---|
| Gute Messung | 10 von 600 | 1,67 % | Nein |
| Schlechte Messung | 305 von 600 | 50,83 % | Ja |

Die schlechte Messung enthält kurze Impulse mit zeitlichen Abständen. Deshalb
muss nicht jeder Abschnitt auffällig sein, obwohl der simulierte schlechte
Betriebszustand die gesamte Messung betrifft. Die vorhandenen Zustandslabels
werden nicht zur Berechnung einer angeblichen Erkennungsquote pro Abschnitt verwendet.

Dateien im Modellordner:

- `autoencoder.npz`: Gewichte, Normalisierung, Merkmalsreihenfolge, Abschnittslänge,
  Schwellenwert, Alarmregel und Versionsangaben in einer Datei. Für die Inferenz
  werden `model.py` und NumPy benötigt; scikit-learn ist nur beim Training erforderlich.
- `training_report.json`: Konfiguration, Trainingsverlust je Epoche, Datenquellen
  mit Seeds und SHA-256-Prüfsummen, Warnungen und Prüfung des gespeicherten Exports.
- `evaluation_report.json`: Ergebnisse der beiden reservierten Funktionstests.

## Aufrufe aus dem Projektordner

Abhängigkeiten für die verwendete Trainingsumgebung:

```powershell
python -m pip install -r autoencoder/requirements.txt
```

Vorhandenes Modell prüfen:

```powershell
python autoencoder/evaluate.py
python -m unittest discover -s autoencoder -p test_model.py
```

Erneut trainieren, ohne einen bestehenden Modellordner zu überschreiben:

```powershell
python autoencoder/train.py --output autoencoder/modell_neu --window-seconds 0.1
python autoencoder/evaluate.py --model autoencoder/modell_neu/autoencoder.npz
```

Eine andere Abschnittslänge benötigt einen neuen Trainingslauf einschließlich
Schwellenwertbestimmung. Sie muss einer ganzen Zahl von Messwerten entsprechen
und die Messung vollständig aufteilen. Die spätere Inferenz liest die Länge
aus dem gespeicherten Modell. Unvollständige Abschnitte werden nicht abgeschnitten;
bei Streaming muss der aufrufende Service sie bis zum nächsten Paket puffern.

## Prüfungen und Grenzen

Die vier automatisierten Tests prüfen bekannte Merkmale konstanter Signale,
Nullsignale, die zeitliche Zuordnung eines Impulses und ungültige Eingaben.
Zusätzlich vergleicht jeder Trainingslauf die Fehler des erneut geladenen
NPZ-Modells mit der scikit-learn-Berechnung auf sämtlichen Validierungsabschnitten.

Die Normaldaten stammen aus demselben synthetischen Generator. Benachbarte
Abschnitte sind abhängig, die zwei guten/schlechten Testmessungen teilen sich
außerdem dasselbe Grundsignal. Die Ergebnisse belegen die Funktion des Prototyps,
keine zuverlässige Fehlerdiagnose an realen Prüfständen. Auch das 99. Perzentil
garantiert keine Fehlalarmrate von 1 % auf neuen Messungen. Für einen realen
Einsatz wären unabhängige reale Normal- und Fehlerdaten sowie eine gesonderte
Bewertung der Alarmregel notwendig.

Dokumentation der verwendeten Bibliothek:
https://scikit-learn.org/1.7/modules/generated/sklearn.neural_network.MLPRegressor.html
