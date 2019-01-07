# errbot-chatopsanything

[![Build Status](https://travis-ci.org/andrewthetechie/errbot-chatopsanything.svg?branch=master)](https://travis-ci.org/andrewthetechie/errbot-chatopsanything)


An Errbot Plugin to make any directory of executables chatops enabled. It passes along arguments directly to your
executable and captures the executables output and return code and returns that to the user via Chat!

You provide a directory and on activation, the plugin searches it for all executable files and adds commands for them. 
It can even get help text if your executable supports -h to provide help test!

But there's more...

Via configuration files you can provide advanced configuration for an executable or even source the executable itself
from a URL.

# Why does this exist?
Every organization develops a set of "scripts" to fix things. These scripts often outlive their expected replacement dates
and can be a pain to setup and configure. Chatops helps even that playing field, making short commands and scripts easier
to find/execute in a shared environment. However, going from a "bash script" to chatops is not easy and there is often 
not time to improve the existing tooling that "works now".

With this plugin, you can take advantage of your organization's library of scripts as Chatops without having to rewrite
each of them!

# Plugin Configuration
## Via Env Variables
* CA_BINPATH - str, full path to the folder you have your Chatops Anything executables in
* CA_CONFPATH - Optional, str, full path to a folder where you have your conf files for advanced configuration. Defaults to $BINPATH/conf.d
* CA_TEMPPATH - Optiona, str, full path to a folder where the plugin can write. Defaults to creating a new temporary directory in the system's tempdir
* CA_EXCLUSIONS - Optional, str, comma separated list of any executables to exclude

## Via Errbot Provisioning
Check out the Errbot guide on how to provide configuration to your bot: http://errbot.io/en/latest/user_guide/provisioning.html

# Command Configuration
Configuration files can be either JSON or YAML. See example_confs for examples of each format. Examples in the documetnation
will be in YAML

## Configure an executable with a custom name, help text or timeout

Chatops Anything lets you configure a binary to have a custom command, a custom timeout, and allows you to provide
help text outside of the binary. 

For example:

    - bin_path: /path/to/our/executable
      name: "Special Script"
      help: "This is a special script"
      timeout: 90
      
would result in a command "special script" that calls "/path/to/our/executabe". Its help text (when running !help from your bot)
will be "This is a special script" (not very helpful at all) and it will timeout if execution takes more than 90s.

Name, Help and timeout are optional fields that you do not have to provide. By default timeout is 30s (you can configure this globally, see above Plugin Config section)
and help will run your executable with -h to gather help text. Name defaults to the filename of the executable.

## Download an executable from a url
Chatops Anything supports downloading your executable from a http/s url. On activation, the plugin will download from the url and 
store it in TEMP_PATH (see Plugin Config on how to set this path). For example:

    - url: https://www.internet.co/my_script.sh
      name: my script
      
Would result in downloading from https://www.internet.co/my_script.sh to our temp path, setting it executable, and
creating a chatops command "my script" that would run it. A URL requires a Name to be provided to work. bin_path will
be ignored if there is a url provided.

**NOTE**: The downloading is not particularly robust at this time. Suggest using a direct link to the file on a service
like Amazon S3 or a similar "artifacts" hosting service for best results. PRs welcome to make downloading more robust!