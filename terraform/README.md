# Terraform-Infrastruktur

Die aktuelle Bereitstellungsanleitung steht in der [zentralen README](../README.md). Alle `.tf`-Dateien dieses Verzeichnisses bilden ein gemeinsames Root-Modul. Keine Dateien einzeln in leere Arbeitsordner verteilen.

- `main.tf`, `providers.tf`, `versions.tf`, `variables.tf`: Projektgrundlage und lokales State-Backend.
- `iothub.tf`, `storage.tf`, `cosmos.tf`: Geräteanbindung und Datenhaltung.
- `registry.tf`, `inference.tf`: Image-Registry und Worker.
- `eventgrid.tf`, `logicapp.tf`, `alarm-workflow.json`: Alarmierung.
- `api.tf`, `frontend.tf`, `keyvault.tf`: API, Dashboard und Secret-Verweise.
- `outputs.tf` und Outputs in den Dienstdateien: Namen und Endpunkte.

`alarm@example.invalid` ist absichtlich kein nutzbarer Empfänger. Vor einer neuen Bereitstellung in `alarm-workflow.json` ersetzen. Die Projekt-Subscription in der Workflow-Vorlage ist anonymisiert; `logicapp.tf` setzt Topic und Subscription dynamisch ein.

`import-logicapp.sh` und `LOGICAPP-IMPORT.md` dokumentieren die einmalige Übernahme bestehender Ressourcen. Das Importskript hat projektspezifische Ziele, die vorher geprüft werden müssen. Nicht für einen leeren Neuaufbau ausführen.

Der Inferenz-Digest dieser Veröffentlichung entspricht dem zuletzt dokumentierten Projekt-Build v3. In einer neuen Registry muss das Image zuerst gebaut und hochgeladen und der neue Digest über eine lokale TFVARS-Datei gesetzt werden.

Kein State, keine Pläne, keine echten TFVARS oder Secrets werden veröffentlicht. `.terraform.lock.hcl` aus dem tatsächlichen Arbeitsverzeichnis nach Prüfung übernehmen. Ein vollständiger Neuaufbau aus diesem Export wurde nicht ausgeführt.
