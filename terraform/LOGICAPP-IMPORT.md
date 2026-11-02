# Übernahme der bestehenden Alarmierung

Stand: 31.10.2026. Azure wurde ausschließlich lesend geprüft. Beide Connectoren
melden Connected. Das Event-Grid-Abonnement meldet Succeeded und filtert auf
Pruefstand.AnomalieErkannt. Es wurden weder Test-E-Mails gesendet noch Ressourcen geändert.

## Dateien und Import

logicapp.tf, alarm-workflow.json und import-logicapp.sh müssen im bestehenden
Cloud-Shell-Verzeichnis ~/clouddrive/cloud-projekt/terraform liegen. Nur diese
neuen Dateien ergänzen, nicht den vorhandenen Terraform-State ersetzen.

```bash
terraform fmt logicapp.tf
bash import-logicapp.sh
```

Das Skript prüft den vorhandenen State, sichert ihn mit restriktiven Dateirechten
und importiert fünf Terraform-Ressourcen. Ein abgebrochener Import kann erneut
gestartet werden. Bereits importierte Adressen werden übersprungen. Der abschließende
Plan wird gespeichert, aber nicht angewendet. Erwartet ist No changes, mögliche
Provider-Normalisierungen müssen vor einem Apply geprüft werden.

Lokal ist kein Terraform installiert. terraform validate und der Vergleich mit
dem bestehenden Cloud-Shell-State stehen deshalb noch aus. Die JSON-Definition
wurde aus Azure übernommen, nicht aus dem Screenshot rekonstruiert.

## Zuständigkeiten und Grenzen

- Direkt in Terraform: Workflow-Ressource, beide API-Verbindungsressourcen,
  Event-Grid-Trigger und E-Mail-Aktion einschließlich Empfänger und Inhalt.
- Im Trigger beschrieben: Topic, Ereignistyp und Callback-Ausdruck. Der
  ApiConnectionWebhook-Connector erzeugt und verwaltet das Ereignisabonnement.
  Es ist KEINE separat importierte azurerm_eventgrid_event_subscription.
- Terraform erkennt damit Änderungen an der Trigger-Konfiguration. Direkte
  Änderungen am erzeugten Abonnement werden durch diesen Plan nicht separat
  auf Drift geprüft. Vollständig direkte Verwaltung aller Einzelressourcen
  würde eine spätere Umstellung auf einen anderen Triggeraufbau erfordern.
- Persönliche OAuth-Autorisierung ist weiterhin interaktiv. parameter_values
  wird nur hierfür ignoriert. Bei einem Neuaufbau müssen beide Verbindungen
  autorisiert werden, Outlook gegebenenfalls mit oauthDelegated im Portal.
  Die Neuinstallation einschließlich OAuth wurde noch nicht getestet.
- prevent_destroy verhindert versehentliche Ersetzungen/Löschungen der fünf
  Bestandteile während der Übernahme. Für den späteren bewussten Projektabbau
  muss dieser Schutz gezielt entfernt werden.

Der importierte Trigger kann eine signierte Callback-Adresse im Terraform-State
und in Plan-Dateien ablegen. State, Backups und Pläne nicht öffentlich weitergeben.
Die hier mitgelieferte JSON-Datei enthält nur @listCallbackUrl(), keinen geheimen URL-Wert.

Nach erfolgreichem No-changes-Plan: Abonnement und Verbindungsstatus prüfen.
Ein neuer Alarmtest versendet eine echte E-Mail und ist ein gesonderter Schritt.

Quellen:
- https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/logic_app_workflow
- https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/api_connection
- https://learn.microsoft.com/en-us/azure/event-grid/monitor-virtual-machine-changes-event-grid-logic-app
