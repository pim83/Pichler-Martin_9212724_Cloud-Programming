# Lesende Ergebnis-API

Python 3.12, Azure Functions Runtime 4, Python-Programmiermodell v2.
Infrastruktur: `terraform/api.tf`. Der API-Code wird separat bereitgestellt.
Der Inferenz-Worker muss für Abfragen gespeicherter Ergebnisse nicht laufen.

## Schnittstelle

- `GET /api/measurements?device_id=pruefstand-01&limit=20`
- `GET /api/measurements/{measurement_id}?device_id=pruefstand-01`

`device_id` ist Pflicht. `limit` ist 1 bis 100, Standard 20.
Die Liste liefert `items`, `count`, `limit`, `has_more` und `order_by`.
Es werden die zuletzt geänderten Ergebnisse angezeigt, maximal 100.
Noch keine Navigation zu älteren Seiten. Die Detailabfrage bleibt per ID möglich.
`updated_at` stammt aus Cosmos `_ts` und bezeichnet die letzte Änderung am
Ergebnis, nicht den Messzeitpunkt. Alarmstatus-Updates ändern diese Reihenfolge.

Antworten: 200 bei Erfolg, 400 für ungültige Parameter, 404 für nicht vorhandene
Messungen, 503 bei Backendfehlern. Keine Schreib- oder Löschendpunkte.
Die Antworten enthalten keine Chunk-Hashes, Cosmos-Systemfelder oder Alarmaufträge.
Ein Blobname ist ein Verweis, kein öffentlicher Downloadlink.

## Zugriff

Cloud-Aufrufe benötigen den Header `x-functions-key`. Schlüssel nicht in URLs,
Screenshots, Quellcode oder Browser-JavaScript speichern. Das ist ein gemeinsamer
Testzugang, keine Benutzer- oder Prüfstandsberechtigung. Wer den Schlüssel besitzt,
kann alle Prüfstände abfragen. Das Frontend verwendet eine serverseitige Anbindung und Passwortanmeldung. CORS wird nicht pauschal freigegeben.

Cosmos wird über die systemseitige Managed Identity der Function App gelesen.
Die Rolle `Cosmos DB Built-in Data Reader` gilt nur für den Ergebniscontainer.
Der separate Function-Host-Speicher verwendet einen von Terraform gesetzten
Speicherschlüssel. Der Schlüssel ist im Terraform-State enthalten. State schützen.

## Lokale Tests

Im Ordner `function_api` mit der eigenen Umgebung:

```powershell
.\.venv\Scripts\python.exe -m unittest test_api -v
```

Tests verwenden simulierte Cosmos-Antworten. Sie prüfen Eingaben, Partitionierung,
Ausgabeumfang, Fehlercodes und die GET-/Function-Key-Bindings. Sie ersetzen nicht
den Cloud-Test von Authentifizierung, Rollen und echter Cosmos-Abfrage.
Der lokale Functions-Host erzwingt Function-Schlüssel standardmäßig nicht.

## Bereitstellung in zwei Schritten

1. `api.tf` in den vorhandenen Cloud-Shell-Terraformordner laden.
   `Microsoft.Web` und gegebenenfalls `Microsoft.Insights` registrieren.
   Danach formatieren, validieren und vollständigen Plan prüfen.
   Erwartet: fünf neue Ressourcen, keine Änderung am Worker.
   `inference_enabled` bleibt `false`.
2. Nach erfolgreichem Apply `function-api.zip` in die Cloud Shell laden.
   Das Paket enthält nur fünf benötigte Dateien im ZIP-Wurzelverzeichnis.
   Im Terraformordner:

```bash
api_name=$(terraform output -raw api_app_name)
az functionapp deployment source config-zip \
  --resource-group rg-cloud-projekt-dev \
  --name "$api_name" \
  --src ~/function-api.zip \
  --build-remote true
```

Der Linux-Remote-Build installiert die gesperrten Python-Abhängigkeiten.
Windows-Pakete aus `.venv` werden nicht hochgeladen. Es wird kein Docker-Image
benötigt. Die Bereitstellung hängt von der regionalen Kapazität und den Quoten des
Students-Abonnements ab. Bei Ablehnung nicht auf einen kostenpflichtigeren Tarif
wechseln, sondern den Fehler zuerst prüfen.

## Cloud-Abnahme

- Aufruf ohne Schlüssel muss abgewiesen werden.
- Liste mit Schlüssel und `device_id=pruefstand-01` muss die vorhandenen
  Cosmos-Ergebnisse anzeigen.
- Detail eines bekannten Ergebnisses mit Cosmos vergleichen, insbesondere
  Messungs-ID, Klassifikation und Anomalieanteil.
- Unbekannte gültige Messungs-ID: 404. Ungültiges Limit: 400.
- POST/DELETE dürfen keine Verarbeitung auslösen.
- Im Application Insights die Abfragen und eventuelle Fehler prüfen.

Das lokale Paket ist vorbereitet. Ein erfolgreicher Azure-Deploy oder Cloud-Test
wird erst nach Ausführung dieser Schritte bestätigt.
