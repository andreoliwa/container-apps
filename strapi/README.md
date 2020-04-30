# Setup

- Create database and user. The user needs superuser privileges to create tables.

        $ pgcli postgresql://postgres:$POSTGRES_PASSWORD@localhost:7712

        postgres@localhost:postgres>
        CREATE DATABASE strapi
        CREATE USER strapi WITH PASSWORD '???'  # See env var STRAPI_DATABASE_PASSWORD
        ALTER USER strapi WITH SUPERUSER;
        GRANT ALL PRIVILEGES ON DATABASE strapi TO strapi;

- [Installing using Docker | Strapi Documentation](https://strapi.io/documentation/3.0.0-beta.x/installation/docker.html)
- If needed, change to debug mode on `strapi/app/config/environments/production/database.json`: [Configurations | Strapi Documentation](https://strapi.io/documentation/3.0.0-beta.x/concepts/configurations.html#database)
- To check logs:

        strapi logs -f
