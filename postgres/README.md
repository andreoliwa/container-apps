# PostgreSQL

## Dump a single database

To dump a database (with date/time on the file name):

```bash
db exec -T postgres12 pg_dump -U postgres [database_name] > /path/to/dump_of_a_single_database_$(date "+%Y-%m-%d-%H-%M-%S").sql
```

## Restore a single database

To restore a database dump:

1. Connect to the container.
   ```bash
   db exec -T postgres12 psql -U postgres
   ```
2. Drop and recreate the database.
   ```sql
   DROP DATABASE [database_name];
   CREATE DATABASE [database_name];
   GRANT ALL PRIVILEGES ON DATABASE [database_name] TO [user_name];
   ```
3. Exit the container and restore the dump on the newly created database.
   ```bash
   db exec -T postgres12 psql -U [user_name] < /path/to/dump_of_a_single_database.sql
   ```
