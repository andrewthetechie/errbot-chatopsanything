import os

from errbot import BotPlugin
from errbot import botcmd
from errbot import arg_botcmd
from errbot import ValidationException

from typing import Dict

class ChatOpsAnything(BotPlugin):
    """ChatOpsAnything is an errbot plugin to allow plain executables in a directory be run via chatops"""
    # botplugin methods, these are not commands and just configure/setup our plugin
    def activate(self) -> None:
        """
        Activates the plugin
        Returns:
            none
        """
        super().activate()

    def deactivate(self) -> None:
        """
        Deactivates the plugin

        Returns:
            None
        """
        super().deactivate()

    def config(self, configuration: Dict) -> None:
        """
        Configures the plugin

        Args:
            configuration (Dict): Dict of configuration variables

        Returns:
            None
        """
        if configuration is None:
            configuration = dict()
        # if we dont have a BIN_PATH, lets try to grab it as an envvar
        if 'BIN_PATH' not in configuration:
            configuration['BIN_PATH'] = os.getenv("COPS_BINPATH")
        # if we dont have EXLCUSIONS, lets try to grab it as an envvar
        # We're expecting a string, comma separated. i.e. bin1,bin2,bin3
        # we split it into a list
        if 'EXCLUSIONS' not in configuration:
            configuration['EXCLUSIONS'] = os.getenv("COPS_EXCLUSIOSN", "").split(",")
        super().configure(configuration)

    def get_configuration_template(self) -> Dict:
        """
        Returns a dictionary used to configure this plugin via chatops

        Returns:
            Configuration Template Dict
        """
        return {"BIN_PATH": "/change/me", # path to the bins we want to setup chatops for
                "EXCLUSIONS": ["bin1", "bin2"] # any bins to exclude, just the names of them
                }

    def check_configuration(self, configuration: Dict) -> None:
        """
        Validates our config
        Args:
            configuration (Dict): Our configuration to validate, might be None

        Returns:
            None

        Raises:
            errbot.ValidationException when the configuration is invalid
        """
        if configuration is None:
            raise ValidationException("Chatops Anything: Invalid Configuration. Config cannot be empty")

        if 'BIN_PATH' not in configuration:
            raise ValidationException("Chatops Anything: Invalid configuration, missing BINPATH")

        # call our method to validate our path. It will also raise ValidationException, and we just re-raise it
        self._validate_bin_path(configuration['BIN_PATH'])

        # we don't really need to validate EXCLUSIONS. If they dont exist in BINPATH, we still will exclude them
        return

    # Helper Functions - these are called by our other methods. they are not chatops commands
    def _validate_bin_path(self, path: str) -> None:
        """
        Validates the passed in path by checking that we can read/write from it and that it contains valid files
        Args:
            path (str): Path to validate

        Returns:
            None

        Raises:
            errbot.ValidationException when out binpath is not valjd
        """
        # TODO: Write this validation
        return



