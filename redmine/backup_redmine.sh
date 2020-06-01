#!/bin/sh
HOME_DIR=$(dirname $(dirname $(dirname $(realpath $0))))

# Deleting old backups
find $HOME_DIR/OneDrive/Backup/ -type f | sort -ur | tail -n+11 | xargs rm 2> /dev/null

# Redmine backup on ~/OneDrive/Backup/
source $HOME_DIR/.config/dotfiles/local.env
$HOME_DIR/.local/bin/docker-compose -f $HOME_DIR/src/postgresql/docker-compose.yml exec -T postgres12 pg_dump -U postgres redmine > $HOME_DIR/OneDrive/Backup/redmine_$(date "+%Y-%m-%d-%H-%M-%S").sql
