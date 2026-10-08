# frozen_string_literal: true

require 'yaml'
require 'fileutils'

def user_config_dir
  base = if Gem.win_platform?
           ENV['APPDATA'] || File.expand_path('~')
         elsif RUBY_PLATFORM.include?('darwin')
           File.join(File.expand_path('~'), 'Library', 'Application Support')
         else
           ENV.fetch('XDG_CONFIG_HOME', File.join(File.expand_path('~'), '.config'))
         end
  File.join(base, 'klayout_gf180mcu')
end

def option_drc
  options_path  = File.join(user_config_dir, 'drc_options.yml')
  defaults_path = File.join(__dir__, 'drc_defaults.yml')

  read_path = File.exist?(options_path) ? options_path : defaults_path
  YAML.safe_load(File.read(read_path))
end

def option_lvs
  options_path  = File.join(user_config_dir, 'lvs_options.yml')
  defaults_path = File.join(__dir__, 'lvs_defaults.yml')

  read_path = File.exist?(options_path) ? options_path : defaults_path
  YAML.safe_load(File.read(read_path))
end

def save_option_drc(options)
  dir = user_config_dir
  FileUtils.mkdir_p(dir)
  File.open(File.join(dir, 'drc_options.yml'), 'w') { |file| file.write(options.to_yaml) }
end

def save_option_lvs(options)
  dir = user_config_dir
  FileUtils.mkdir_p(dir)
  File.open(File.join(dir, 'lvs_options.yml'), 'w') { |file| file.write(options.to_yaml) }
end
