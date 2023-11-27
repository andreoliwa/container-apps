# paperless-ngx

- [paperless-ngx/paperless-ngx: A supercharged version of paperless: scan, index and archive all your physical documents](https://github.com/paperless-ngx/paperless-ngx)
- [Paperless-ngx](https://docs.paperless-ngx.com/)

# Setup

- Using docker-compose: [Setup — Paperless-ng 1.5.0 documentation](https://paperless-ng.readthedocs.io/en/latest/setup.html#install-paperless-from-docker-hub)
- Connect to the local database:
  ```
  invoke db-connect
  ```
- Create user and database:
  ```
  CREATE USER paperless WITH PASSWORD 'paperless';
  CREATE DATABASE paperless;
  GRANT ALL PRIVILEGES ON DATABASE paperless TO paperless;
  ```
