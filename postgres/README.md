# PostgreSQL

## Dump a single database

To dump a database on the backup dir, with date/time on the file name:

```bash
cd ~/container-apps
invoke --dry db-dump [database_name]
```

## Restore a single database

To restore a database dump:

1. Connect to the container.
   ```bash
   db exec postgres14 psql -U postgres
   ```
2. Drop and recreate the database.
   ```sql
   DROP DATABASE [database_name];
   CREATE DATABASE [database_name];
   GRANT ALL PRIVILEGES ON DATABASE [database_name] TO [user_name];
   ```
3. Exit the container and restore the dump on the newly created database.
   ```bash
   db exec -T postgres14 psql -U [user_name] -f /var/backups/path/to/dump_of_a_single_database.sql
   ```

## Upgrade Postgres

[How to Upgrade PostgreSQL in Docker and Kubernetes - CloudyTuts](https://www.cloudytuts.com/tutorials/docker/how-to-upgrade-postgresql-in-docker-and-kubernetes/)
