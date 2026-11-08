# Cloud-basierte Prüfstandsüberwachung

Studienprojekt Cloud Programming, Phase 2: Simulierte Beschleunigungsdaten gelangen über IoT Hub zum Autoencoder in Container Apps. Blob Storage und Cosmos DB speichern Rohdaten und Ergebnisse. Event Grid und Logic Apps versenden Alarme. Eine Function API versorgt das passwortgeschützte Flask-Dashboard in App Service.

Geprüft wurden Normalmessungen (10/600 auffällige Fenster, kein Alarm), Anomaliemessungen (305/600, Alarm-E-Mail), API und Dashboard-Zugriffsschutz. Ein vollständiger Neuaufbau in einem leeren Abonnement wurde nicht getestet. Der Prototyp verwendet eine Worker-Replica und einen gemeinsamen Dashboard-Zugang. Lasttests mit zehn Geräten und eine Validierung mit realen Sensordaten stehen aus.

## Verzeichnisse

| Ordner | Inhalt |
|---|---|
| `messdatengenerator` | Generatoren und zwei synthetische Testmessungen |
| `autoencoder` | Training, gemeinsame Merkmalsberechnung, Modell v2 und Berichte |
| `iot_sender` | MQTT-Sender für den registrierten Prüfstand |
| `inference_service` | Worker, Dockerfile, Speicherzugriff, Alarmversand und Tests |
| `function_api` | Lesende HTTP-API und Tests |
| `web_frontend` | Flask-Dashboard, Secret-Einrichtung und Tests |
| `terraform` | Azure-Ressourcen und Importhilfe für bestehende Logic Apps |

Modell und synthetische Testmessungen sind enthalten. Große Trainingsdaten werden bei Bedarf erzeugt. Zugangsdaten und Terraform-Zustandsdateien bleiben außerhalb des Repositorys.

## Voraussetzungen

Python 3.12, Docker mit Linux-Containern, Azure CLI und Terraform >= 1.16.4 und < 2. AzureRM-Version siehe `terraform/versions.tf`. Benötigt werden ein Azure-Abonnement mit ausreichenden Ressourcen- und Rollenberechtigungen sowie ein Microsoft-365-Postfach.

Die Befehle verwenden Bash. Docker-Builds lokal ausführen, die übrigen Azure-Schritte beispielsweise in Cloud Shell.

## Lokale Daten und Tests

Vom Repository-Hauptverzeichnis aus getrennte virtuelle Umgebungen für Training, Worker, API und Dashboard verwenden. Beispiel für das Training:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r autoencoder/requirements.txt
python -m unittest discover -s autoencoder -p 'test_*.py' -v
```

Tests entsprechend für `iot_sender`, `inference_service`, `function_api` und `web_frontend` ausführen, jeweils nach Installation ihrer Requirements. Der Worker verwendet `requirements.lock.txt`. Lokale Tests simulieren Azure-Zugriffe. Details stehen in den jeweiligen Ordner-READMEs.

Optional Trainingsdaten und ein neues Modell erzeugen:

```bash
python messdatengenerator/generate_training_data.py
python autoencoder/train.py --output autoencoder/modell_neu
```

## Bereitstellung: Konfiguration vorbereiten

1. Mit `az login` anmelden und das Zielabonnement wählen:

```bash
az account set --subscription "<Abonnementname-oder-ID>"
export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
```

2. Projektspezifische Einstellungen anpassen:
   - `terraform/variables.tf`: Region und Ressourcengruppe.
   - `iot_sender/send_measurement.py`: `EXPECTED_HUB` laut Terraform-Output.
   - `web_frontend/setup_dashboard_secrets.py`: `SUBSCRIPTION`, `VAULT`, `GROUP`, `FUNCTION` laut eigenen Outputs.
   - `terraform/alarm-workflow.json`: `alarm@example.invalid` durch das Empfängerpostfach ersetzen. Topic-/Subscription-Vorlagen überschreibt Terraform dynamisch.
   - `terraform/logicapp.tf`: gegebenenfalls Verbindungsanzeigename.

`import-logicapp.sh` dient ausschließlich der Übernahme vorhandener Ressourcen. Dafür zunächst Abonnement und Ressourcengruppe im Skript prüfen.

3. Ressourcenanbieter registrieren, da die Provider-Konfiguration dies nicht automatisch übernimmt:

```bash
for provider in Microsoft.Devices Microsoft.Storage Microsoft.DocumentDB Microsoft.ContainerRegistry Microsoft.App Microsoft.OperationalInsights Microsoft.Insights Microsoft.EventGrid Microsoft.Logic Microsoft.Web Microsoft.KeyVault Microsoft.ManagedIdentity; do
  az provider register --namespace "$provider" --wait
done
```

## Terraform, Modell und Container

Terraform verwendet ein lokales Backend. Bei bestehenden Ressourcen den zugehörigen State weiterverwenden. State und Pläne können Secrets enthalten und dürfen nicht ins Repository.

```bash
cd terraform
terraform init
terraform fmt -check
terraform validate
```

Die nach `init` erzeugte `.terraform.lock.hcl` prüfen und committen. In der Ausgangskopie fehlte sie, daher ist die bisherige Providerauflösung nicht exakt dokumentiert.

Für einen Neuaufbau zuerst die Registry bereitstellen:

```bash
terraform plan -target=azurerm_container_registry.inference -out=registry.tfplan
terraform show -no-color registry.tfplan
terraform apply registry.tfplan
terraform output -raw container_registry_name
terraform output -raw container_registry_login_server
```

`-target` nur für diesen Bootstrap verwenden, danach vollständige Pläne. Lokal aus dem Repository-Hauptverzeichnis das Image bauen:

```bash
registry_name="<container_registry_name>"
registry_host="<container_registry_login_server>"
az acr login --name "$registry_name"
docker build --platform linux/amd64 -f inference_service/Dockerfile -t "$registry_host/pruefstand-inferenz:v3" .
docker push "$registry_host/pruefstand-inferenz:v3"
```

Den eigenen Push-Digest in `terraform/inference.auto.tfvars` eintragen. Der voreingestellte Projekt-Digest ist in einer neuen Registry nicht vorhanden:

```hcl
inference_enabled = false
inference_image_digest = "sha256:<Digest-des-eigenen-Builds>"
```

Dann die gesamte Infrastruktur planen und nach Sichtprüfung bereitstellen:

```bash
terraform plan -out=deployment.tfplan
terraform show -no-color deployment.tfplan
terraform apply deployment.tfplan
terraform output
```

Logic-App-Verbindungen im Portal interaktiv autorisieren. Falls der Trigger vorher fehlschlägt, anschließend erneut planen/anwenden. Der Connector verwaltet das Event-Grid-Abonnement.

Das Modell aus dem Repository-Hauptverzeichnis hochladen. Das angemeldete Konto benötigt eine Blob-Datenrolle, unabhängig von den Worker-Berechtigungen:

```bash
storage_account="$(terraform -chdir=terraform output -raw measurement_storage_account)"
az storage blob upload --auth-mode login --account-name "$storage_account" --container-name modelle --name autoencoder.npz --file autoencoder/modell_v2/autoencoder.npz --overwrite false
```

Der Modell-Hash ist in `inference_service/MODEL_SHA256.txt` und der Terraform-Konfiguration festgelegt. Bei Modellwechsel beide kontrolliert aktualisieren. Bestehende Modellblobs nicht unbemerkt überschreiben.

## API, Secrets und Dashboard bereitstellen

ZIPs dürfen keine virtuelle Umgebung, Tests, Secrets oder übergeordnete Verzeichnisebene enthalten. In einer Shell mit `zip` aus dem Repository-Hauptverzeichnis:

```bash
mkdir -p dist
(cd function_api && zip ../dist/function-api.zip function_app.py service.py host.json requirements.txt)
(cd web_frontend && zip -r ../dist/web-frontend.zip app.py requirements.txt templates static)
group="$(terraform -chdir=terraform output -raw resource_group_name)"
api_name="$(terraform -chdir=terraform output -raw api_app_name)"
web_name="$(terraform -chdir=terraform output -raw frontend_app_name)"
az functionapp deployment source config-zip --resource-group "$group" --name "$api_name" --src dist/function-api.zip --build-remote true
```

Das Secret-Skript mit angepassten Konstanten interaktiv in Cloud Shell ausführen. Die Key-Vault-Rolle des Benutzers muss bereits wirksam sein:

```bash
python -m venv /tmp/dashboard-setup-venv
source /tmp/dashboard-setup-venv/bin/activate
python -m pip install -r web_frontend/requirements.txt
python web_frontend/setup_dashboard_secrets.py
deactivate
az webapp deploy --resource-group "$group" --name "$web_name" --src-path dist/web-frontend.zip --type zip
```

Das Skript fragt das Passwort verdeckt ab und speichert Hash, Sitzungs- und Function-Schlüssel. Bestehende Secrets werden übersprungen. Secret-Werte nicht veröffentlichen. Das Dashboard benötigt aufgelöste Key-Vault-Referenzen.

## Gerät, Test und Abschluss

Das Gerät `pruefstand-01` separat im IoT-Hub-Portal registrieren. Die Geräteverbindung verdeckt im Sender eingeben, keinen Hub-Administratorschlüssel verwenden.

`inference_enabled = true` in der lokalen TFVARS-Datei setzen, planen und anwenden. Nach Worker-Start und Modellladung in der Sender-Umgebung testen:

```bash
python iot_sender/send_measurement.py
python iot_sender/send_measurement.py --send
python iot_sender/send_measurement.py --file messdatengenerator/beispieldaten/messung_schlecht.npy --send
```

Cosmos-Ergebnisse, Blob-Archiv, Logic-App-Lauf, E-Mail, Dashboard und Application Insights prüfen. Der erste Befehl prüft lokal, der zweite sendet die Normalmessung, der dritte die Anomaliemessung.

Danach `inference_enabled = false` setzen, planen/anwenden und abschließend `terraform plan` prüfen. Andere Ressourcen verursachen weiterhin Kosten.

## Betriebsannahmen

Die [Kostenkalkulation aus dem Azure-Preisrechner](Kostenkalkulation/ExportedEstimate.xlsx) enthält die geschätzten Betriebskosten und die zugrunde gelegten Dienstkonfigurationen.

Der Prototyp nutzt eine B1-Einheit. Zehn Prüfstände mit stündlichen 60-Sekunden-Messungen benötigen mindestens 432.000 Nachrichteneinheiten täglich und deshalb zwei B1-Einheiten (`iothub_units = 2`). Ein automatischer Sendezeitplan ist nicht enthalten. F1 und gemeinsamer Passwortzugang dienen der Demonstration, Schlüsselrotation erfolgt manuell.

## Dokumentation der verwendeten Werkzeuge

- [Terraform](https://developer.hashicorp.com/terraform/docs)
- [Azure IoT SDK für Python](https://github.com/Azure/azure-iot-sdk-python)
- [scikit-learn](https://scikit-learn.org/stable/)
- [NumPy](https://numpy.org/doc/)
- [Azure SDK für Python](https://learn.microsoft.com/en-us/azure/developer/python/sdk/azure-sdk-overview)
- [Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/)
- [Flask](https://flask.palletsprojects.com/)

## Veröffentlichung

Nur diesen Ordnerinhalt hochladen. Vorher `git status --short` und vorgemerkte Dateien prüfen. `.gitignore` ersetzt keine Inhaltsprüfung. Die private PDF mit dem Dashboard-Passwort nicht veröffentlichen.
