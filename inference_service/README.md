# Inferenz-Service für den Cloud-Prototyp

Der Inferenz-Service wurde als v3-Image bereitgestellt und mit synthetischen Messungen geprüft. Das verwendete Modell liegt in `autoencoder/modell_v2/autoencoder.npz`. Für Bereitstellungsreihenfolge und aktuelle Grenzen gilt die zentrale README.

## Verarbeitung

1. Empfang über den eingebauten Event-Hubs-kompatiblen Endpunkt des IoT Hubs.
2. Geräte-ID aus den authentifizierten IoT-Hub-Systemeigenschaften übernehmen.
3. Schema, Länge, Achsen, Abtastrate, Nummerierung und SHA-256 prüfen.
4. Pro Sekunde zehn Analysefenster bilden, neun Merkmale berechnen und dieselbe
   Skalierung, Gewichte und Schwellenwerte wie im Training verwenden.
5. Rohdaten, Metadaten und Fensterergebnisse gemeinsam in einem temporären Blob
   speichern. Vorher keinen Empfangs-Checkpoint setzen.
6. Sobald alle Abschnitte vorliegen, die Werte sortiert zu einer NPY-Datei
   zusammenfügen. Originalwerte bleiben exakt erhalten.
7. Die Datei nach `messdaten/<device>/<measurement-id>.npy` schreiben, anschließend
   das Ergebnis in Cosmos DB speichern und erst dann temporäre Abschnitte löschen.

Wir verwenden NPY wie die Quelldateien. Es gibt eine Rohdatendatei je Messung.
Metadaten, Modell-Hash, Fensteranzahl und Bewertung stehen im Ergebnisdokument.
Die Namen enthalten absichtlich die eindeutige Messungs-ID statt einer
laufenden Nummer. Dies vermeidet Konflikte zwischen Übertragungen.

Prototypgrenze: höchstens 60 Abschnitte, 10000 Hz, drei Achsen, float32 Little
Endian. Genau eine aktive Service-Replica und eine aktive Revision betreiben.
Callbacks werden innerhalb dieses Prozesses serialisiert. Mehrere Replicas
erfordern zusätzlich einen getesteten Schutz der Zusammenführung gegen
gleichzeitige Verarbeitung und sind noch nicht freigegeben.

## Verhalten bei Fehlern

- Fehlende Abschnitte erzeugen kein vollständiges Ergebnis. Vorhandene Daten
  bleiben temporär erhalten und unterliegen der Sieben-Tage-Bereinigungsregel.
- Identische Wiederholungen ergeben keine zweite Messung. Widersprüchliche
  Wiederholungen werden abgewiesen.
- Ungültige Nachrichten werden als Rohdaten unter `temporaer/rejected/`
  isoliert. Partition und Sequenznummer werden ohne Zugangsdaten protokolliert.
- Bei Azure-Speicherfehlern beendet sich der Worker ohne neuen Checkpoint.
  Container Apps muss ihn neu starten. Bereits gespeicherte Abschnitte bleiben
  bestehen. Das letzte unbestätigte Ereignis wird erneut verarbeitet.
- Abgeschlossenes Archiv und Ergebnis bleiben erhalten, wenn das Aufräumen
  fehlschlägt. Bei erneuter Zustellung wird die Bereinigung wiederholt.
- Modelländerungen während einer Messung werden abgelehnt. Vor einem Modell-
  Update offene Messungen abschließen oder mit neuer Messungs-ID neu senden.
- IoT Hub hält Ereignisse aktuell einen Tag vor. Längere Ausfälle können eine
  neue Übertragung vom lokalen Rechner notwendig machen. Es gibt keine
  unbegrenzte Wiederherstellungszusage.

## Dateien

| Datei | Zweck |
|---|---|
| processor.py | Prüfung, Inferenz, Zusammenführung und Abschlussreihenfolge |
| azure_store.py | Azure Blob Storage und Cosmos DB |
| worker.py | Modell laden, IoT-Hub-Empfang und Checkpoints |
| local_check.py | Verarbeitung mit lokalen Dateispeichern statt Azure |
| test_processor.py | Wiederholung, Neustart, Datenfehler und Speicherausfälle |
| Dockerfile | Linux-Container mit Python 3.12 und nicht privilegiertem Benutzer |
| requirements.lock.txt | Konkret installierte Bibliotheksversionen |

`autoencoder/model.py` wird direkt weiterverwendet, damit Training und Cloud
dieselbe Merkmalsberechnung und Inferenz nutzen.

## Lokal ausprobieren

In PowerShell im Projektordner:

```powershell
.\iot_sender\.venv\Scripts\python.exe -m unittest inference_service.test_processor -v
.\iot_sender\.venv\Scripts\python.exe -m inference_service.local_check
```

Das zweite Kommando speichert beide Beispielmessungen und ihre Ergebnisse unter
`inference_service/local_check/`. Es werden keine Daten an Azure gesendet.
Erwartet: normal 10/600 auffällig, Alarm false, gestört 305/600, Alarm true.
Jeder Lauf erzeugt neue Messungs-IDs. Die Ergebnisse sind synthetische
Funktionsnachweise, keine Validierung realer Diagnosequalität.

## Voraussetzungen für die Azure-Bereitstellung

Terraform beschreibt die folgenden Voraussetzungen für den Worker:

- Azure Container Registry für das Image.
- Cosmos DB for NoSQL mit Datenbank `pruefstand`, Container `ergebnisse`,
  Partition Key `/device_id`. Serverless-Tarif für den Prototyp.
- Private Blob-Ablage `checkpoints` im vorhandenen Speicherkonto. Keine
  Lifecycle-Löschung für diese Checkpoints konfigurieren.
- IoT-Hub-Consumergruppe `inferenz`, getrennt vom CLI-Testmonitor.
- Empfangsberechtigung nur `ServiceConnect` als IoT-Hub-Zugriffsrichtlinie.
  Deren Event-Hubs-kompatible Verbindungszeichenfolge als Container-Secret
  einbinden. Keine Geräte- oder iothubowner-Zugangsdaten verwenden.
- Verwaltete Identität des Workers mit Blob-Lesezugriff auf `modelle`,
  Blob-Schreibzugriff auf `temporaer`, `messdaten` und `checkpoints`,
  sowie Cosmos DB Built-in Data Contributor auf die Ergebnisdatenbank.
- Container Apps ohne öffentlichen HTTP-Eingang. Im Testbetrieb min_replicas=1
  und max_replicas=1. Standardmäßig inference_enabled=false mit min_replicas=0.
  Ohne Skalierungstrigger startet der ausgeschaltete Worker nicht automatisch.
  Der Theorievergleich bleibt Dauerbetrieb für zehn Prüfstände. Praktisch testen
  wir mit einem Prüfstand und nur den erforderlichen Messungen.

Umgebungsvariablen des Containers:

| Variable | Inhalt |
|---|---|
| BLOB_ACCOUNT_URL | https://stpruefa23c51c917a9.blob.core.windows.net |
| COSMOS_URL | Endpoint des Cosmos-Kontos |
| MODEL_BLOB | autoencoder.npz |
| MODEL_SHA256 | SHA-256 der freigegebenen Modelldatei, siehe MODEL_SHA256.txt |
| IOTHUB_EVENT_CONNECTION_STRING | Geheimnis für den IoT-Empfang mit EntityPath |

Der Build-Kontext ist der Projektordner. Das Dockerfile kopiert nur benötigten
Code. Der Modellblob wird zur Laufzeit geladen und vor Verwendung geprüft.
Die Befehle für den lokalen Docker-Build, den Push zur Registry und die Bereitstellung stehen in der [zentralen README](../README.md). Alarmierung, API und Dashboard sind im Projekt umgesetzt.

Quellen:
- https://learn.microsoft.com/en-us/python/api/overview/azure/eventhub-checkpointstoreblob-readme
- https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/quickstart-python
- https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-endpoints

