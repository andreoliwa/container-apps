require 'rubygems'
require 'rake'
require 'rufus-scheduler'
require 'yaml'

# Add this to avoid error uninitialized constant Redmine::IMAP
# https://github.com/docker-library/redmine/issues/175#issuecomment-537648982
require 'redmine/imap.rb'

load File.join(Rails.root, 'Rakefile')

config = YAML.load_file('/usr/src/redmine/config/configuration.yml')
smtp_settings = config['default']['email_delivery']['smtp_settings']

# Enter the Docker container and check the rake file for the parameters:
# redmine exec redmine bash -i
# vim /usr/src/redmine/lib/tasks/email.rake

# https://support.google.com/mail/answer/7126229?hl=en
ENV['host'] = 'imap.gmail.com'
ENV['port'] = '993'
ENV['ssl'] = 'SSL'
ENV['username'] = smtp_settings['user_name']
ENV['password'] = smtp_settings['password']
ENV['move_on_success'] = 'success'
ENV['move_on_failure'] = 'failure'
ENV['TZ'] = 'Europe/Berlin'
ENV['project'] = config['imap_project']
ENV['allow_override'] = 'all'

# https://github.com/jmettraux/rufus-scheduler
scheduler = Rufus::Scheduler.new

# Check emails every minute
scheduler.interval '1m' do
  task = Rake.application['redmine:email:receive_imap']
  task.reenable
  task.invoke
end
