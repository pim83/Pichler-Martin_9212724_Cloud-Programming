# Kleine Prüfstand-Oberfläche

Serverseitiges Flask-Frontend für Azure App Service (Linux, Python 3.12).
Die bestehende Function API bleibt die einzige Datenquelle. Keine direkten
Cosmos-Zugriffe und keine Function-Schlüssel im Browser.

## Umfang

- Übersicht der höchstens 100 zuletzt aktualisierten Messungen pro Prüfstand
- Anzahl geladener, normaler und auffälliger Ergebnisse
- Filter Alle / Normal / Auffällig, manuelle Aktualisierung
- Messungs-ID, Status, Anteil auffälliger Fenster, letzte Ergebnisaktualisierung
- Detailansicht mit Fensteranzahl, Grenzwerten, Messdatenumfang

Die Zahlen beziehen sich auf die geladenen Ergebnisse, nicht den gesamten Bestand.
Die Zeit ist die Aktualisierung des Ergebnisses, nicht der ursprüngliche Messzeitpunkt.
Keine Rohdatenvisualisierung, Downloads oder schreibenden Funktionen.

## Bereitstellungsstand

Das Dashboard wurde in Azure App Service bereitgestellt und der Passwortschutz wurde geprüft. F1 ist für den Projekt-Testbetrieb vorgesehen. Neuaufbauten benötigen eigene Secrets und passende Abonnementkontingente.

## Gemeinsames Projektpasswort

Der Tutor öffnet die Dashboard-Adresse und gibt das Projektpasswort ein.
Kein Azure-, GitHub- oder Hochschulkonto erforderlich. Das gemeinsame Passwort
berechtigt zum Lesen, nicht zum Ändern oder Löschen. Jeder mit diesem Passwort
hat denselben Zugriff. Nur für dieses Projekt verwenden und nach der Bewertung
ändern, falls die Zugangsdaten in einer weitergegebenen Dokumentation stehen.

Die Prüfung erfolgt serverseitig gegen einen scrypt-Hash. Das Klartextpasswort
wird weder im Quellcode noch in Cookies gespeichert. Die signierte Sitzung ist
zwei Stunden gültig. Cookies sind Secure, HttpOnly und SameSite=Lax.
Anmeldung und Abmeldung verwenden CSRF-Tokens. Ein Passwortwechsel macht
Sitzungen mit dem alten Hash ungültig. Logout entfernt das Browser-Cookie,
eine bereits gestohlene Cookie-Kopie bleibt bis Ablauf oder Schlüsselwechsel
verwendbar (keine serverseitige Sitzungssperrliste).

Fehlende Zugangskonfiguration sperrt das Dashboard. Die Function API bleibt
zusätzlich schlüsselgeschützt. Besucher ohne Anmeldung verursachen keine
API-/Cosmos-Abfragen, können aber weiterhin Last auf der Anmeldeseite erzeugen.

Einstellungen:

| Name | Wert |
| --- | --- |
| RESULTS_API_URL | https://func-pruef-api-a23c51c917a9.azurewebsites.net/api |
| RESULTS_API_KEY | Key-Vault-Referenz auf einen Function-Schlüssel |
| DASHBOARD_PASSWORD_HASH | scrypt-Hash über werkzeug.security.generate_password_hash erzeugen, als Secret hinterlegen |
| DASHBOARD_SESSION_KEY | Unabhängiger zufälliger Schlüssel mit mindestens 32 Zeichen, z. B. secrets.token_urlsafe(48), als Secret hinterlegen |
| PUBLIC_DEVICE_IDS | pruefstand-01 (bestehender Einstellungsname, jetzt hinter Passwortschutz) |
| SCM_DO_BUILD_DURING_DEPLOYMENT | true |

Für eine neue Bereitstellung beide Dashboard-Secrets und den
Function-Schlüssel über Key-Vault-Referenzen bereitstellen. Keine Secrets in
Terraform-Variablendateien, Screenshots oder Repository-Dateien eintragen.
App Service muss HTTPS erzwingen. Keine zusätzliche Easy-Auth-Anmeldung nötig.
Die Managed Identity der Web-App benötigt Leserechte auf die betreffenden
Secrets, keine Cosmos- oder Blob-Schreibrechte. Function-Schlüsselrotation
muss mit der Kopie in Key Vault abgestimmt werden.

Die Anmeldebegrenzung erlaubt fünf Passwortprüfungen pro Minute insgesamt
pro Prozess. Sie gilt unabhängig von Cookies und IP-Headern für alle Besucher.
Daher können fremde Anmeldeversuche auch den Tutor kurzzeitig blockieren.
Die Begrenzung wird bei Neustart zurückgesetzt. Betrieb mit genau einem
Gunicorn-Worker und einer App-Service-Instanz. Vor Skalierung ist ein gemeinsamer
Limiter-Speicher nötig. Dies ist kein vollständiger DDoS- oder Kostenschutz.

Nur freigegebene Prüfstände sind erreichbar. Modell-Hashes, Blob-Pfade und
Alarmereignisse werden nicht angezeigt. Auch künftige Ergebnisse des freigegebenen
Prüfstands sind nach Anmeldung sichtbar. X-Robots-Tag bittet Suchmaschinen um
Nichtindexierung und ersetzt keinen Zugriffsschutz.

Startkommando auf App Service:

```text
gunicorn --workers 1 --bind=0.0.0.0 --timeout 60 app:app
```

Bereitstellungsreihenfolge und Voraussetzungen: [zentrale README](../README.md).

## Lokale Prüfungen

Im Ordner web_frontend:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_app.py
```

17 Tests prüfen Anmeldung, Abmeldung, Cookies, CSRF, Anmeldebegrenzung, fehlende
Secrets, Prüfstand-Freigabe, abgewiesene Schreibanfragen, Filter, Detaildarstellung und HTML-Escaping sowie
Fehlerantworten und serverseitige Schlüsselverwendung. Die Tests ersetzen
keinen Azure-Integrationstest. Sie verwenden eine simulierte API.

Das ZIP enthält ausschließlich app.py, requirements.txt, templates und static.
Keine virtuelle Umgebung, Tests oder Zugangsdaten.
