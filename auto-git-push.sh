#!/bin/bash

# ?? Zeitstempel für Commit-Nachricht
timestamp=$(date +"%Y-%m-%d %H:%M:%S")

# ?? Prüfen, ob Änderungen vorhanden sind
if [[ -n $(git status --porcelain) ]]; then
  echo "?? Änderungen gefunden – bereit zum Hochladen…"

  git add .
  git commit -m "Auto-Commit am $timestamp"
  git push

  echo "✅ Änderungen erfolgreich gepusht!"
else
  echo "?? Keine Änderungen – nichts zu tun."
fi
