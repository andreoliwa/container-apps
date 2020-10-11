# Redmine

- Docker Hub: https://hub.docker.com/_/redmine
- GitHub: https://github.com/docker-library/redmine
- Docs: https://github.com/docker-library/docs/tree/master/redmine

# Setup

- Copy `configuration.sample.yml` to `configuration.yml` and fill in the variables
- Spin up the [shared PostgreSQL](../postgres/docker-compose.yml) instance with `db up -d`
- Connect to the database with one of these commands:
  - `pgcli postgresql://postgres:$POSTGRES_PASSWORD@localhost:7712`
  - `db exec postgres12 psql -U postgres`
- Create the redmine user with:
  ```sql
  CREATE USER redmine;
  ALTER USER redmine WITH PASSWORD '<type the value of REDMINE_DB_PASSWORD here>';
  CREATE DATABASE redmine;
  GRANT ALL PRIVILEGES ON DATABASE redmine TO redmine;
  ```
- Connect to the database with the newly created userone of these commands:
  - `pgcli postgresql://redmine:$REDMINE_DB_PASSWORD@localhost:7712`
  - `db exec postgres12 psql -U redmine`
- [Restore the database if you have a backup](../postgres/README.md)
- Spin up Redmine with `redmine up` or `redmine up -d`
- Wait for the server to come up, then [login with the default admin/admin user/pass](https://github.com/docker-library/docs/tree/master/redmine#accessing-the-application)
- Start using Redmine: Change the password, create users, create projects...
