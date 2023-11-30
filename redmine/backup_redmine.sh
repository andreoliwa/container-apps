#!/usr/bin/bash
# To add this backup to the crontab:
# - crontab -e
# - Add this line: 0 5 * * * /root/container-apps/redmine/backup_redmine.sh
# - crontab -l

HOME_DIR=$(dirname $(dirname $(dirname $(realpath $0))))
BACKUP_DIR="$HOME_DIR/OneDrive/Backup/$(hostname)/postgres14"
mkdir -p $BACKUP_DIR

echo "Remove empty backups"
find "$BACKUP_DIR" -type f -size 0 -print -delete

echo "Delete old backups"
find "$BACKUP_DIR" -type f ! -size 0 | sort -ur | tail -n+11 | xargs rm 2> /dev/null
set -e

source $HOME_DIR/.config/dotfiles/local.env
echo 'Dumping the database...'
$(which docker-compose) -f \
    $HOME_DIR/container-apps/postgres/compose.yml \
    exec -T postgres14 pg_dump -U postgres redmine > \
    "$BACKUP_DIR/redmine_$(date "+%Y-%m-%d-%H-%M-%S").sql"
ls -l "$BACKUP_DIR"
