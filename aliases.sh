#!/usr/bin/env bash
# Hetzner doesn't support the new Docker CLI ("docker compose" without dash)
# keep-sorted start
alias db='docker compose -f ~/container-apps/postgres/compose.yaml'
alias focalboard='docker compose -f ~/container-apps/focalboard/compose.yaml'
alias mayan='docker compose -f ~/container-apps/mayan/compose.yaml'
alias mysql='docker compose -f ~/container-apps/mysql/compose.yaml'
alias redmine='docker compose -f ~/container-apps/redmine/compose.yaml'
alias rss='docker compose -f ~/container-apps/tt-rss/compose.yaml'
alias strapi='docker compose -f ~/container-apps/strapi/compose.yaml'
alias wikijs='docker compose -f ~/container-apps/wikijs/compose.yaml'
# keep-sorted end
