# Lokaler Versand zum IoT Hub

Das kommentierte `send_measurement.py` liest eine NPY-Messdatei mit ihrer
gleichnamigen JSON-Datei. Standard ist die normale Testmessung aus
`messdatengenerator/beispieldaten/`. Es verändert die Quelldateien nicht.

## Start unter Windows

PowerShell im Projektordner `Phase_2` öffnen. Die isolierte Umgebung liegt
unter `iot_sender/.venv`. Sie benötigt keine Aktivierung.

Lokaler Probelauf mit einem Abschnitt, ohne Netzwerkzugriff:

```powershell
.\iot_sender\.venv\Scripts\python.exe .\iot_sender\send_measurement.py --limit 1
```

Versand eines einzelnen Abschnitts:

```powershell
.\iot_sender\.venv\Scripts\python.exe .\iot_sender\send_measurement.py --send --limit 1
```

Das Skript fragt verdeckt nach der Geräte-Verbindungszeichenfolge für
`pruefstand-01`. Alternativ liest es `IOTHUB_DEVICE_CONNECTION_STRING` aus
der Prozessumgebung. Nicht im Quellcode speichern oder in Screenshots zeigen.
Im Azure-Portal den Projekt-IoT-Hub öffnen und unter Geräte `pruefstand-01`
auswählen. Dort die primäre Verbindungszeichenfolge des Geräts kopieren.
Keinen gemeinsamen Verwaltungsschlüssel des Hubs verwenden.

Eine vollständige Messung senden:

```powershell
.\iot_sender\.venv\Scripts\python.exe .\iot_sender\send_measurement.py --send
```

Die gestörte Messung auswählen:

```powershell
.\iot_sender\.venv\Scripts\python.exe .\iot_sender\send_measurement.py --send --file .\messdatengenerator\beispieldaten\messung_schlecht.npy
```

Für eine neue Installation mit Python 3.12:

```powershell
python -m venv iot_sender/.venv
.\iot_sender\.venv\Scripts\python.exe -m pip install -r iot_sender/requirements.txt
```

## Empfang prüfen

Vor dem Versand in der Azure Cloud Shell starten:

```bash
az iot hub monitor-events \
  --hub-name "iot-pruefstand-a23c51c917a9" \
  --device-id "pruefstand-01" \
  --subscription "Azure for Students" \
  --properties app sys --timeout 0
```

Die Nutzdaten sind binär und keine lesbare JSON-Nachricht. Entscheidend sind
Geräte-ID und Nachrichteneigenschaften mit der passenden Messungs-ID.
Der Monitor ersetzt keine Prüfung der späteren Blob-Speicherung.
Mit Strg+C beenden.

## Nachrichtenformat v1

- Body: 10000 Zeilen mit jeweils x, y, z, float32 Little Endian in C-Reihenfolge.
- Größe: 120000 Byte pro Sekunde, insgesamt 60 Nachrichten für 60 Sekunden.
- Eigenschaften: Messungs-ID, nullbasierte Abschnittsnummer, Gesamtzahl,
  Abtastrate, Wertezahl, Position, Achsen, Einheit, Datenformat und SHA-256.
- Message-ID: Messungs-ID plus Abschnittsnummer. Correlation-ID: Messungs-ID.
- Keine Zustandslabels und keine Trainingsinformationen im Nachrichteninhalt.
- MQTT über TLS/WebSockets auf Port 443, eine Verbindung pro Übertragung.
- Eine Sekunde Pause zwischen bestätigten Sendungen begrenzt die Last.
  Dadurch dauert die Wiedergabe etwas länger als die Messung.

Jeder Start erzeugt eine neue Messungs-ID. Ein Teiltest bleibt ausdrücklich
unvollständig. Bei einem Fehler wird abgebrochen, bereits angenommene
Nachrichten können im Hub liegen. Ein Neustart beginnt eine neue Übertragung.
Automatische Wiederaufnahme einer abgebrochenen Messung ist noch nicht umgesetzt.

## Abgrenzung zur späteren Cloud-Verarbeitung

Die Bestätigung im Sender bedeutet nur, dass IoT Hub die Nachricht angenommen
hat. Zusammenführung, dauerhafte Zwischenablage, Vollständigkeitsprüfung,
Inferenz und Bereinigung temporärer Abschnitte werden erst im Cloud-Service
implementiert. IoT Hub ist kein dauerhaftes Messdatenarchiv.

Der Empfänger muss Messungen anhand von authentifizierter Geräte-ID und
Messungs-ID zuordnen, Prüfsummen prüfen und doppelte Abschnitte erkennen.
Nach erfolgreicher Speicherung der vollständigen Messung kann er temporäre
Abschnitte entfernen. Unvollständige Messungen benötigen eine Ablaufregel.

## Lokale Tests

```powershell
.\iot_sender\.venv\Scripts\python.exe -m unittest discover -s iot_sender -p test_sender.py -v
```

Geprüft werden beide Testmessungen, verlustfreie Wiederherstellung,
Abschnittszuordnung, Prüfsummen, SDK-Nachrichten sowie identische Merkmale
und Modellfehler nach abschnittsweiser Verarbeitung. Kein Azure-Zugriff.

Referenz: https://github.com/Azure/azure-iot-sdk-python
