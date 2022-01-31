# MySQL

Docker sandbox to play with MySQL.

## Restore dumps

To restore a database dump:

1. Start MySQL.
   ```bash
   mysql up -d
   ```
2. Enter the container.
   ```bash
   docker exec -it mysql5-7 bash
   ```
3. Connect to the local server inside the container, and type the password when asked.
   ```bash
   mysql -p
   ```
4. Run the `source` command for each dump you want to import (`.create` = table creation, `.sql` = table data).
   ```bash
   source /var/backups/path-to-file.create
   source /var/backups/path-to-file.sql
   ```
5. Connect to the database and run queries:
   ```bash
   mycli mysql://root:$MYSQL_PASSWORD@localhost
   ```
