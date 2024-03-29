# Redmine

- Docker Hub: https://hub.docker.com/_/redmine
  - https://github.com/docker-library/redmine
  - Docs: https://github.com/docker-library/docs/tree/master/redmine
- GitHub: https://github.com/redmine/redmine

# Setup

1. Copy `configuration.sample.yml` to `configuration.yml` and fill in the variables.
   Or copy the YAML file from the live production server.
2. Spin up the [shared PostgreSQL](../postgres/docker-compose.yml) instance with `db up -d`
3. Connect to the database with one of these commands:
   - `pgcli postgresql://postgres:$POSTGRES_PASSWORD@localhost:7714`
   - `db exec postgres14 psql -U postgres`
4. Create the Redmine user with:
   ```sql
   CREATE USER redmine;
   ALTER USER redmine WITH PASSWORD '<type the value of REDMINE_DB_PASSWORD here>';
   CREATE DATABASE redmine;
   GRANT ALL PRIVILEGES ON DATABASE redmine TO redmine;
   ```
5. Connect to the database with the newly created userone of these commands:
   - `pgcli postgresql://redmine:$REDMINE_DB_PASSWORD@localhost:7714`
   - `db exec postgres14 psql -U redmine`
6. [Restore the database if you have a backup](../postgres/README.md)
7. Copy files from one server to the other, e.g. `scp -r old-server:/path/to/Redmine new-server:/path/to/`
8. Spin up Redmine with `redmine up` or `redmine up -d`
9. Wait for the server to come up, then [login with the default admin/admin user/pass](https://github.com/docker-library/docs/tree/master/redmine#accessing-the-application) or with an existing user
10. Start using Redmine: Change the password, create users, create projects...
11. Make sure the backups are working and running on the crontab: `~/container-apps/redmine/backup_redmine.sh`
