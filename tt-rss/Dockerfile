# TODO fix: use this in the future: https://git.tt-rss.org/fox/ttrss-docker-compose

# https://github.com/docker-library/docs/blob/master/php/README.md#with-apache
FROM php:8-apache
RUN apt-get update
ENV TERM xterm-256color

# Install PostgreSQL PDO https://github.com/docker-library/php/issues/221#issuecomment-254153971
RUN apt-get install -y libpq-dev libicu-dev cron sudo git && \
    docker-php-ext-configure pgsql -with-pgsql=/usr/local/pgsql && \
    # Install intl to avoid this error:
    # PHP UConverter class is missing, it's provided by the Internationalization (intl) module.
    docker-php-ext-install pdo pdo_pgsql pgsql intl && \
    groupadd ttrss -g 1001 && \
    useradd ttrss -m -u 1001 -g ttrss && \
    git clone --progress --verbose https://git.tt-rss.org/fox/tt-rss.git /var/www/html/ && \
    chown -R ttrss:ttrss /var/www/html

# https://github.com/docker-library/php/blob/d97098c8c6af46ae1211e65ff052278ab39ba45c/7.2/stretch/apache/Dockerfile
ENV APACHE_RUN_GROUP=ttrss
ENV APACHE_RUN_USER=ttrss

# https://git.tt-rss.org/fox/tt-rss/wiki/UpdatingFeeds
# https://serverfault.com/questions/449651/why-is-my-crontab-not-working-and-how-can-i-troubleshoot-it
COPY ./cron.allow /etc/
COPY ./cron-update-feeds /etc/cron.d/
COPY ./start-cron-apache.sh /usr/local/bin/
COPY config.php .

CMD ["start-cron-apache.sh"]
