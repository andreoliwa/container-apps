# [Tiny Tiny RSS](https://tt-rss.org/)

## Install

[Installing and upgrading](https://git.tt-rss.org/fox/tt-rss/wiki/InstallationNotes)

- Fill the screen "Database settings" with values from `config.php`, from the variables `DB_*`:
- Connect to the PostgreSQL database:

        pgcli postgresql://postgres:$POSTGRES_PASSWORD@localhost:7710/postgres

- Create user and database on the pgcli prompt using SQL commands:

        CREATE USER ttrss WITH PASSWORD 'ttrss';
        CREATE DATABASE ttrss;
        GRANT ALL ON DATABASE ttrss TO ttrss;

- Click on "Test configuration" and fix problems until the connection works.
- Click on "Initialize database".
