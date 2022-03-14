# paperless-ng

- [jonaswinkler/paperless-ng: A supercharged version of paperless: scan, index and archive all your physical documents](https://github.com/jonaswinkler/paperless-ng)
- [Paperless — Paperless-ng 1.5.0 documentation](https://paperless-ng.readthedocs.io/en/latest/index.html)

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
