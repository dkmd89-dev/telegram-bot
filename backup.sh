#!/bin/bash

# Backup-Skript für MusicCenter-Daten
# Ziel: /mnt/320gb/backups

# Konfiguration
BACKUP_ROOT="/mnt/320gb/backups"
SOURCE_DIRS=(
    "/mnt/media/musiccenter/library"
    "/mnt/media/musiccenter/navidrome"
    "/mnt/media/musiccenter/yt_music_bot"
)
LOG_FILE="$BACKUP_ROOT/backup_log.txt"
MAX_BACKUPS=5  # Anzahl der aufzubewahrenden Backups

# Aktuelles Datum für Backup-Ordner
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_DIR="$BACKUP_ROOT/musiccenter_backup_$TIMESTAMP"

# Funktion für Logging
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Überprüfung der Mount-Points
check_mountpoint() {
    if ! mountpoint -q "$1"; then
        log "FEHLER: $1 ist nicht gemountet!"
        exit 1
    fi
}

# Alte Backups aufräumen
cleanup_old_backups() {
    log "Aufräumen alter Backups (behalte die neuesten $MAX_BACKUPS)..."
    cd "$BACKUP_ROOT" || exit
    ls -td musiccenter_backup_* | tail -n +$(($MAX_BACKUPS + 1)) | xargs rm -rf
}

# Hauptskript
main() {
    log "=== Starte Backup-Prozess ==="
    
    # Überprüfe ob Zielverzeichnis existiert
    mkdir -p "$BACKUP_ROOT"
    
    # Überprüfe Mount-Points
    check_mountpoint "/mnt/media"
    check_mountpoint "/mnt/320gb"
    
    # Erstelle Backup-Verzeichnis
    mkdir -p "$BACKUP_DIR"
    
    # Backup durchführen
    for dir in "${SOURCE_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            dir_name=$(basename "$dir")
            log "Backup von $dir wird erstellt..."
            tar -czf "$BACKUP_DIR/${dir_name}_$TIMESTAMP.tar.gz" -C "$(dirname "$dir")" "$(basename "$dir")"
            if [ $? -eq 0 ]; then
                log "Backup von $dir erfolgreich erstellt."
            else
                log "FEHLER beim Backup von $dir!"
            fi
        else
            log "WARNUNG: Verzeichnis $dir existiert nicht und wird übersprungen!"
        fi
    done
    
    # Aufräumen alter Backups
    cleanup_old_backups
    
    # Berechne Größe des Backups
    backup_size=$(du -sh "$BACKUP_DIR" | cut -f1)
    log "Backup abgeschlossen. Größe: $backup_size"
    log "Backup gespeichert in: $BACKUP_DIR"
    log "=== Backup-Prozess beendet ==="
}

main
