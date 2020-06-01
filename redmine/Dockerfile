FROM redmine:4
WORKDIR /usr/src/redmine

COPY ./configuration.yml config/configuration.yml

RUN apt-get update && \
    apt-get --yes install vim && \
    bundle add 'rufus-scheduler'

# https://www.redmine.org/projects/redmine/wiki/RedmineReceivingEmails#Schedule-email-receiving-with-Rufus-Scheduler
COPY ./check_email.rb config/initializers/check_email.rb

# Add manually downloaded custom themes to the existing ones
COPY ./themes public/custom-themes
RUN mv public/custom-themes/* public/themes/ && \
    chown -R redmine:redmine public/
