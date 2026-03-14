# Zammad

Modern open-source helpdesk/ticket system. Replaces Redmine for issue tracking, email-based ticket creation, and
calendar integration.

## Prerequisites

- PostgreSQL 17 running (`cd ../postgres && docker compose up -d postgres17`)
- Shared Redis running (`cd ../redis && docker compose up -d`)
- Environment variables set:

```bash
export ZAMMAD_DB_PASSWORD=<password>
```

## Setup

```bash
# Create database and user
invoke zammad-setup

# Start the stack
invoke zammad-up

# Open http://localhost:8008
```

## Usage

```bash
invoke zammad-up          # Start and follow logs
invoke zammad-up --pull   # Pull latest images first
invoke zammad-down        # Stop
```

## Architecture

- **zammad-init** — One-shot: runs DB migrations and Elasticsearch index setup
- **zammad-railsserver** — Main Rails application
- **zammad-nginx** — Nginx reverse proxy (port 8008)
- **zammad-scheduler** — Background job processor (Sidekiq)
- **zammad-websocket** — WebSocket server for real-time updates
- **zammad-elasticsearch** — Full-text search (Elasticsearch 8)
- **zammad-memcached** — Response caching

## Integrations (configured via Zammad Admin UI)

- **Email** — Channels → Email: add IMAP/SMTP channels for Gmail or Fastmail
- **iCal** — Built-in at `/ical/tickets/...` (per user/group), subscribe in any calendar app
- **Telegram** — Channels → Telegram: add bot token from BotFather, requires HTTPS

## Migration from Redmine

Migration is implemented as an invoke task.

### Configuration

Copy `zammad.toml.example` to `zammad.toml` (gitignored) and fill in your instance's state/priority names:

```bash
cp zammad/zammad.toml.example zammad/zammad.toml
# edit zammad/zammad.toml
```

### Running the migration

```bash
# Run the migration (import mode is enabled/disabled automatically)
invoke zammad-migrate

# Rebuild the search index after migration
invoke zammad-reindex
```

All credentials can be passed as flags (`--redmine-db-pass`, `--zammad-token`) or via `POSTGRES_PASSWORD` /
`ZAMMAD_TOKEN` env vars.

### Re-importing from scratch

```bash
invoke zammad-wipe     # deletes all imported tickets, users, groups, custom fields
invoke zammad-migrate  # import mode toggled automatically
invoke zammad-reindex
```

### Post-migration verification checklist

After running the migration, verify the following manually in the Zammad UI:

- [ ] Ticket states match the Redmine statuses (Admin → Ticket States)
- [ ] Ticket priorities are correct (Admin → Ticket Priorities)
- [ ] Imported group exists and agents are members (Admin → Groups)
- [ ] Users were imported with correct names and emails (Admin → Users)
- [ ] Custom fields appear on tickets (Admin → Objects)
- [ ] A sample of tickets has correct creation dates (requires import mode was active)
- [ ] Journal notes appear as articles on tickets
- [ ] Search returns results after `invoke zammad-reindex` completes

## Backup

- PostgreSQL `zammad` database: extend `postgres/cron-backup.sh` (see spec Section 6)
- Elasticsearch index: rebuildable via `rake zammad:searchindex:rebuild`
- File storage: `zammad-storage` volume (minimal if attachment-free)

## Tips and Learnings

### Articles (notes/comments) are immutable

Zammad does not allow editing articles after creation — this is by design for audit trail purposes. There is no edit
button in the UI. The only way to correct a note is via a direct database update:

```bash
# Find the article
invoke db-connect zammad --version 17 --psql --command="SELECT id, body FROM ticket_articles WHERE ticket_id = <TICKET_ID> ORDER BY id;"

# Update it
invoke db-connect zammad --version 17 --psql --command="UPDATE ticket_articles SET body = '<corrected text>' WHERE id = <ARTICLE_ID>;"
```

### Search delay after migration

Elasticsearch takes several minutes to index all tickets after a migration. During this time, full-text search may
return no results or partial results — this is normal. To trigger reindexing manually:

```bash
invoke zammad-reindex
```

You can monitor Elasticsearch indexing progress at `http://localhost:9200/_cat/indices?v`.
