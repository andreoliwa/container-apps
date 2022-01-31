#!/usr/bin/env bash
# Using the new Docker CLI ("docker compose" without dash)
alias db='docker compose -f ~/container-apps/postgres/docker-compose.yml'
alias rss='docker compose -f ~/container-apps/tt-rss/docker-compose.yml'
alias mayan='docker compose -f ~/container-apps/mayan/docker-compose.yml'
alias strapi='docker compose -f ~/container-apps/strapi/docker-compose.yml'
alias redmine='docker compose -f ~/container-apps/redmine/docker-compose.yml'
alias wikijs='docker compose -f ~/container-apps/wikijs/docker-compose.yml'
alias mysql='docker compose -f ~/container-apps/mysql/docker-compose.yml'
