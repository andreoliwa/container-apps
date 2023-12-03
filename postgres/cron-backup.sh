#!/usr/bin/env bash
# To add this backup to the crontab:
# - crontab -e
# - Add this line: 0 5 * * * /root/container-apps/postgres/cron-backup.sh <DATABASE>
# - crontab -l

# $HOME doesn't work in crontab, so we need to set it manually
HOME_DIR=$(dirname $(dirname $(dirname $(realpath $0))))
BACKUP_DIR="$HOME_DIR/OneDrive/Backup/$(hostname)/postgres14"
mkdir -p $BACKUP_DIR

DATABASE=$1
if [ -z "$DATABASE" ]; then
    echo "No database name provided"
    exit 1
fi
echo "Database name: $DATABASE"

echo "Remove empty backups"
find "$BACKUP_DIR" -type f -size 0 -print -delete

# TODO find another way of deleting old backups per database instead of mixing all of them
# echo "Delete old backups"
# find "$BACKUP_DIR" -type f ! -size 0 | sort -ur | tail -n+11 | xargs rm 2> /dev/null

set -e
# This file has the environment variables needed to connect to the database
source $HOME_DIR/.config/dotfiles/local.env
OUTPUT_FILE="${BACKUP_DIR}/${DATABASE}_$(date "+%Y-%m-%d-%H-%M-%S").sql"
echo "Dumping the database to ${OUTPUT_FILE}..."
COMMAND="$(which docker-compose) -f $HOME_DIR/container-apps/postgres/compose.yml \
    exec -T postgres14 pg_dump -U postgres $DATABASE"
echo "Running command: $COMMAND"
$COMMAND > $OUTPUT_FILE
ls -lhtr "${BACKUP_DIR}"
