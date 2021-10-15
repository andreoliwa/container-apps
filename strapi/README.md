# Setup

1.  Create user and database. The user needs superuser privileges to create tables.

    ```
    $ pgcli postgresql://postgres:$POSTGRES_PASSWORD@localhost:7714

    postgres@localhost:postgres>
    # See env var STRAPI_DATABASE_PASSWORD
    CREATE USER strapi WITH PASSWORD '???'
    ALTER USER strapi WITH SUPERUSER;

    # Create the database only if not restoring from a backup
    CREATE DATABASE strapi
    GRANT ALL PRIVILEGES ON DATABASE strapi TO strapi;
    ```

2.  [Installing using Docker | Strapi Documentation](https://strapi.io/documentation/3.0.0-beta.x/installation/docker.html)
3.  If needed, change to debug mode on `strapi/app/config/environments/production/database.json`: [Configurations | Strapi Documentation](https://strapi.io/documentation/3.0.0-beta.x/concepts/configurations.html#database)
4.  To check logs:
    ```
    strapi logs -f
    # or
    inv up-logs strapi
    ```
5.  The `app/api` and `app/components` subdirectories contains info about the content types.
    If these dirs are deleted, the database itself is not enough to restore types.
6.  To update Strapi, maybe this will work: [Update Strapi version - Strapi Developer Documentation](https://strapi.io/documentation/developer-docs/latest/update-migration-guides/update-version.html).
