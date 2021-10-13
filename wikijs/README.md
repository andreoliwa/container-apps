# Setup

1. Connect to the container.
   ```bash
   inv db-connect
   ```
2. Create user/database:
   ```
   CREATE USER wikijs WITH PASSWORD '<password here>';
   CREATE DATABASE wikijs;
   GRANT ALL PRIVILEGES ON DATABASE wikijs to wikijs;
   ```
3. Connect as the WikiJS user:
   ```
   inv db-connect --user wikijs --password-env WIKIJS_PASSWORD --database wikijs
   ```
4. Run this on the database:
   ```
   CREATE EXTENSION pg_trgm;
   ```
5. Start WikiJS:
   ```
   inv up-logs wikijs
   ```
6. Navigate to http://localhost:8004/ to complete the setup.
7. Configure Git storage:
   - [Git | Wiki.js](https://docs.requarks.io/storage/git)
   - [Admin | My Personal Notes](http://localhost:8004/a/storage)
8. Choose "Database - PostgreSQL" as the search engine: [Admin | My Personal Notes](http://localhost:8004/a/search)
