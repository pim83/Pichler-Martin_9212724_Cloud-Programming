"""Einmalige Einrichtung in Azure Cloud Shell (Bash), keine Secret-Ausgaben."""
import getpass
import json
import os
import secrets
import subprocess
import sys
import tempfile

from werkzeug.security import generate_password_hash

SUBSCRIPTION = "9a3ac9e4-7982-4f63-9247-6e7178233e1f"
VAULT = "kv-pruef-a23c51c917a9"
GROUP = "rg-cloud-projekt-dev"
FUNCTION = "func-pruef-api-a23c51c917a9"


def az(*args):
    result = subprocess.run(
        ["az", *args, "--subscription", SUBSCRIPTION, "--only-show-errors"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        # CLI-Ausgaben können Secret-Werte enthalten, deshalb nicht weitergeben.
        raise RuntimeError("Azure-Aufruf fehlgeschlagen. Anmeldung und Key-Vault-Rollen prüfen. "
                           "Neue Rollen benötigen gegebenenfalls einige Minuten.")
    return result.stdout.strip()


def save_secret(name, value):
    if not value:
        raise RuntimeError("Leerer Secret-Wert, Speicherung abgebrochen.")
    # mkstemp erstellt unter Linux eine Datei mit Modus 0600. Nicht im clouddrive.
    fd, path = tempfile.mkstemp(prefix="dashboard-secret-", dir="/tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        az("keyvault", "secret", "set", "--vault-name", VAULT,
           "--name", name, "--file", path, "--encoding", "utf-8", "-o", "none")
    finally:
        os.unlink(path)
    print(f"Gespeichert: {name}")


def main():
    existing = set(json.loads(az("keyvault", "secret", "list", "--vault-name", VAULT,
                                "--query", "[].name", "-o", "json")))
    names = ("dashboard-password-hash", "dashboard-session-key", "results-api-key")
    for name in names:
        if name in existing:
            print(f"Bereits vorhanden, unverändert: {name}")
            continue
        if name == "dashboard-password-hash":
            if not sys.stdin.isatty():
                raise RuntimeError("Bitte direkt im interaktiven Cloud-Shell-Terminal ausführen.")
            password = getpass.getpass("Neues Projektpasswort (mindestens 16 Zeichen): ")
            repeated = getpass.getpass("Projektpasswort wiederholen: ")
            if password != repeated or not 16 <= len(password) <= 256:
                raise RuntimeError("Passwörter stimmen nicht überein oder Länge liegt nicht zwischen 16 und 256 Zeichen.")
            value = generate_password_hash(password, method="scrypt")
            del password, repeated
        elif name == "dashboard-session-key":
            value = secrets.token_urlsafe(48)
        else:
            value = az("functionapp", "keys", "list", "--resource-group", GROUP,
                       "--name", FUNCTION, "--query", "functionKeys.default", "-o", "tsv")
            if not value or value == "null":
                raise RuntimeError("Kein standardmäßiger Function-Schlüssel gefunden.")
        save_secret(name, value)
    print("Einrichtung abgeschlossen. Keine Secret-Werte wurden ausgegeben.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        # OSError kann Dateipfade, aber keine Secret-Inhalte enthalten.
        print(f"Abbruch: {error}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("Einrichtung abgebrochen.", file=sys.stderr)
        sys.exit(1)
