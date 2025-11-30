# Focalboard

- [Focalboard - Personal Edition](https://www.focalboard.com/download/personal-edition/docker/)
- [mattermost-community/focalboard: Focalboard is an open source, self-hosted alternative to Trello, Notion, and Asana](https://github.com/mattermost-community/focalboard)
- [API Documentation](https://htmlpreview.github.io/?https://github.com/mattermost/focalboard/blob/main/server/swagger/docs/html/index.html)

Focalboard is an open source, multilingual, self-hosted project management tool that's an alternative to Trello, Notion, and Asana.

# Setup

1. Start Focalboard:
    ```bash
    focalboard up -d
    ```
2. Navigate to http://localhost:8005/ to access your Focalboard server.
3. Create your first account (the first user becomes the admin).
4. Start creating boards, cards, and organizing your projects!

# Usage

The data is stored in `~/OneDrive/Apps/Focalboard/` using SQLite database.

# Upgrading

To upgrade to the latest version:

```bash
focalboard pull
focalboard up -d
```
