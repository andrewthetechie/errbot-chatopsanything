# errbot-chatopsanything
An Errbot Plugin to make any directory of executables chatops enabled


# Configuration
## Via Env Variables
* CA_BINPATH - str, full path to the folder you have your Chatops Anything executables in
* CA_CONFPATH - Optional, str, full path to a folder where you have your conf files for advanced configuration. Defaults to $BINPATH/conf.d
* CA_TEMPPATH - Optiona, str, full path to a folder where the plugin can write. Defaults to creating a new temporary directory in the system's tempdir
* CA_EXCLUSIONS - Optional, str, comma separated list of any executables to exclude