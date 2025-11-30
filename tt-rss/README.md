# Personal News Intelligence Stack

A lightweight, hackable, **self-hosted news dashboard** that consolidates RSS, Twitter/X, Telegram, Substack, YouTube,
Reddit, and more — and lets me rank by **my keywords**, not social popularity.

- Officially maintained
  repo: [tt-rss/tt-rss: A free, flexible, open-source, web-based news feed (RSS/Atom/other) reader and aggregator.](https://github.com/tt-rss/tt-rss)

## Install

[Installation Guide | Tiny Tiny RSS Documentation](https://tt-rss.org/docs/Installation-Guide.html)

- Fill the screen "Database settings" with values from `config.php`, from the variables `DB_*`:
- Connect to the PostgreSQL database:

          pgcli postgresql://postgres:$POSTGRES_PASSWORD@localhost:7710/postgres

- Create user and database on the pgcli prompt using SQL commands:

          CREATE USER ttrss WITH PASSWORD 'ttrss';
          CREATE DATABASE ttrss;
          GRANT ALL ON DATABASE ttrss TO ttrss;

- Click on "Test configuration" and fix problems until the connection works.
- Click on "Initialize database".

## Plugins

Plugins are installed in `$CONTAINER_APPS_DATA_DIR/ttrss/data/tt-rss/plugins.local/`.
They are usually Git repositories clones in that directory.

Plugins configured:

- [GitHub - supahgreg/ttrss-af-notifications: Adds a filter action to receive JavaScript-based notifications.](https://github.com/supahgreg/ttrss-af-notifications?tab=readme-ov-file)

## Requirements & Goals

- **Self-hosted**.
- **Open source** components.
- **Lightweight** (fits 2 vCPU / 4 GB RAM).
- **Mobile-friendly** (Android + iOS via clients).
- **Keyword-first intelligence**:
    - Filter and **score** articles by keywords/regex.
    - Maintain keyword sets via UI (no config editing).
    - Optional Bayesian learning (secondary to explicit rules).
- Ingest from **non-RSS platforms** (Twitter/X, Telegram, Substack, YouTube, Reddit, Instagram…).

## Chosen Architecture

- **Tiny Tiny RSS (TTRSS)** — Core reader with **filters, scoring, labels**, plugins, and a responsive UI.
    - Uses official maintained images from [tt-rss/tt-rss](https://github.com/tt-rss/tt-rss) (GitHub Container Registry)
- **RSSHub + Redis** — Feed generator for non-RSS sources; enormous route catalog, good caching.
    - `rsshub-internal`: The actual RSSHub service (port 1200)
    - `rsshub`: Nginx proxy on port 80 (works around TT-RSS port stripping bug)
- **Postgres** — Backend for TTRSS.
- **Docker Compose** — One-file bring-up on macOS.

### Why this combo?

- **Keyword and regex scoring** are first-class in TTRSS.
- **UI-driven filter management** lets me evolve rules easily.
- **RSSHub** covers substantially more sources and options than RSS-Bridge, and its URLs map 1:1 across environments,
  making migration trivial.

## Running Locally (macOS LAN)

1. `docker compose up -d`
2. Open **http://localhost:8002/tt-rss** → login with admin credentials
3. **Enable plugins:**
    1. Click hamburger menu (☰) or username in top right
    2. Go to **Preferences**
    3. Click **Plugins** tab
    4. Enable: `af_readability`, `fever`, `share`, etc.
    5. For first-party plugins not bundled: use built-in plugin installer in Preferences → Plugins
4. Add feeds from **http://rsshub/** (RSSHub proxy):
    1. `http://rsshub/telegram/channel/<channel>`
    2. `http://rsshub/twitter/user/<handle>`
    3. `http://rsshub/substack/<site>`
    4. `http://rsshub/youtube/channel/<id>`
    5. `http://rsshub/reddit/subreddit/<name>`
    6. Browse all routes: http://localhost:8006/ or https://docs.rsshub.app/
5. On Android (same Wi-Fi), open `http://<mac-lan-ip>:8002/tt-rss` in the browser or:
    1. Use the **Tiny Tiny RSS** Android app
    2. Use **Fiery Feeds** or **Reeder** via the **Fever** plugin:
        - Server: `http://<mac-lan-ip>:8002/plugins/fever/`
        - Username/Password: your TT-RSS credentials

## Keyword-First Workflow

- **Filters → Create** rules like:
    - _Content matches_ `(AI|Llama|frontier model|EU AI Act)` → **score +15**, **label: AI/Policy**
    - _Title matches_ `(?i)\b(NBA|transfer|matchday)\b` → **score −20**, optionally **mark as read**
    - _Feed title is_ `"Trusted Analyst"` → **score +50**
- Sort by **Score (desc)** to surface what matters.
- Use **Labels** to both tag and audit which rules triggered.
- Optional **Bayesian plugin**: mark a sample of good/bad items to add adaptive scoring (secondary to explicit rules).

## Moving to the cloud

- Reuse Postgres in Docker (already running).
- Put services behind **Caddy/Traefik** with HTTPS.
- Replace local URLs:
    - `http://localhost:8002/tt-rss` → `https://news.yourdomain.tld/tt-rss`
    - `http://localhost:8006/` → `https://rsshub.yourdomain.tld/`
- Update `TTRSS_SELF_URL_PATH` in compose.yaml to match your public URL
- If some RSSHub routes need it, configure **PROXY_URI** or cookies per docs.

## Alternatives considered (and why discarded)

- **RSS-Bridge**: lighter and simple, but **less comprehensive** than RSSHub and more manual per-source tuning. RSSHub’s
  catalog and cache model fit better and provide a smoother **local→cloud drop-in** path.
- **FreshRSS**: Modern UI, active development, good mobile support, cleaner codebase than TTRSS.
    - **Fatal limitations for my use case**:
        - ❌ **No article scoring system** - Cannot assign importance/priority scores to articles based on keywords
        - ❌ **No sort by score** - Cannot surface important articles to the top of the feed
        - ❌ **No global filters** - Filters are per-feed only, not across all feeds simultaneously
        - ❌ **No auto-labeling based on keywords** - Cannot automatically categorize/tag articles
        - ❌ **No extensions exist** - Searched extensively (GitHub, forums, Docker Hub), zero plugins provide scoring
          functionality
        - ❌ **Feature requests pending since 2021** - GitHub
          Discussion [#3337](https://github.com/FreshRSS/FreshRSS/discussions/3337) shows global filter actions and
          auto-labeling requested in January 2021, still not implemented as of November 2024
    - **Verdict**: Excellent for chronological reading, but fundamentally cannot do keyword-based importance ranking
      which
      is my core requirement #5 from "Personal News Intelligence Stack" above.
    - **Why this matters**: I need to filter 100+ feeds down to the 5-10 articles that matter to ME based on MY
      keywords,
      not what's popular on social media. TTRSS's scoring system is the only solution that does this.
- **Miniflux (Go)**: love the simplicity and Go performance, but advanced **UI-managed filtering/scoring** is more
  limited for this use case.
- **NewsBlur**: strong training features, but **heavier** and less customizable in the way I want (my keywords over
  social/trending signals).
- **Feedly** (hosted): not self-hosted; emphasis on social/trending; paid features for some workflows.

## Setup Instructions

### Prerequisites

1. **PostgreSQL 17** must be running (see `../postgres/compose.yml`)
2. **Environment variables** must be set (add to your shell profile):

    ```bash
    export CONTAINER_APPS_DATA_DIR=~/OneDrive/Apps/
    export TTRSS_DB_NAME=ttrss
    export TTRSS_DB_USER=ttrss
    export TTRSS_DB_PASS=<your-secure-password>
    export POSTGRES_PASSWORD=<postgres-superuser-password>
    ```

    **Important**: Make sure these are exported in your current shell before running docker compose!

### First-Time Setup

#### Option 1: Automated Setup (Recommended)

1. **Run the setup task**:
    ```bash
    cd ~/container-apps
    invoke setup-ttrss
    ```
    This will:
    1. Start PostgreSQL 17
    2. Create the TT-RSS database and user
    3. Create data directories
2. .**Start TT-RSS stack**:
    ```bash
    cd tt-rss
    docker compose up -d
    ```
3. **Check logs** to ensure everything started correctly:
    ```bash
    docker compose logs -f
    ```
4. **Access TT-RSS** on http://localhost:8002/tt-rss
5. **Access RSSHub**:
    1. Direct access (for browsing routes): http://localhost:8006/
    2. In TT-RSS feeds, use: `http://rsshub/...` (no port needed, proxy handles it)
    3. Browse available routes at https://docs.rsshub.app/

## Notes

- Some RSSHub routes (Twitter/X, Instagram, YouTube) may require **proxies, cookies, or tokens** to be reliable due to
  rate limits and anti-bot measures.
- Keep Redis enabled for caching; it reduces load and speeds up feeds.
- Back up volumes: `${CONTAINER_APPS_DATA_DIR}/ttrss/{data,config,redis}` and PostgreSQL database.
- Export OPML from TTRSS for feed portability.
