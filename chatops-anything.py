import glob
from hashlib import md5
import itertools
import os
from pathlib import Path
from shutil import rmtree
import stat
from tempfile import gettempdir
from typing import Dict
from typing import Iterable

from errbot.backends.base import Message as ErrbotMessage
from errbot import BotPlugin
from errbot import Command
from errbot import ValidationException


class ChatOpsAnything(BotPlugin):
    """ChatOpsAnything is an errbot plugin to allow plain executables in a directory be run via chatops"""
    def __init__(self, bot, name: str = None) -> None:
        """
        Calls super init and adds a few plugin variables of our own. This makes PEP8 happy
        """
        super().__init__(bot, name)
        # HASH is used to identify the plugin and for uniqueness
        # generate a md5 hash of os.times() and grab 10 characters of it, just for easy uniqueness
        self.HASH = md5(f"{os.times()}".encode("utf-8")).hexdigest()[:10]
        self.BIN_PATH = None  # typing: Path
        self.CONFIG_PATH = None  # typing: Path
        self.TEMP_PATH = None  # typing: Path
        self.log.debug("Done with init")

    # botplugin methods, these are not commands and just configure/setup our plugin
    def activate(self) -> None:
        """
        Activates the plugin
        Returns:
            none
        """
        super().activate()
        self.log.debug(f"In activate BIN_PATH {self.config['BIN_PATH']}, CONFIG_PATH {self.config['CONFIG_PATH']}, "
                       f"TEMP_PATH {self.config['TEMP_PATH']}")

        self.TEMP_PATH = Path(self.config['TEMP_PATH'])
        exec_configs = {}
        if self.config['CONFIG_PATH'] is not None:
            self.CONFIG_PATH = Path(self.config['CONFIG_PATH'])
            config_files = self._get_all_confs_in_path(self.CONFIG_PATH)
            self.log.info(f"Found configs at {self.CONFIG_PATH}. Loading them now. This can take a while...")
            exec_configs = self._load_exec_configs(config_files)

        self.BIN_PATH = Path(self.config['BIN_PATH'])
        executables = self._get_all_execs_in_path(self.BIN_PATH)
        self.log.info(f"Found executables at {self.BIN_PATH}")
        self.log.info(f"Configuring executables and gathering help")
        commands = list()
        for executable in executables:
            # create a new command for the bot
            commands.append(Command(lambda plugin, msg, args: self._run_command(executable, args, msg),
                            name=executable.name,
                            doc=self._get_help(executable)))
        # create a dynamic plugin for all of our executables
        self.create_dynamic_plugin("Chatops Binaries", tuple(commands))

    def deactivate(self) -> None:
        """
        Deactivates the plugin

        Returns:
            None
        """
        try:
            if 'TMP_CLEANUP' in self.config and self.config['TMP_CLEANUP']:
                self._cleanup_tempdir(self.config['TEMP_PATH'])
            # destroy our dynamic plugin cleanly
            self.destroy_dynamic_plugin(f"Chatops Binaries")
        except Exception as error:
            # This is a VERY broad except, but we want to make sure deactivate is called
            self.log.exception(str(error))
        super().deactivate()

    def configure(self, configuration: Dict) -> None:
        """
        Configures the plugin

        Args:
            configuration (Dict): Dict of configuration variables

        Returns:
            None
        """
        self.log.debug("Starting Config")
        if configuration is None:
            configuration = dict()
        # if we dont have a BIN_PATH, lets try to grab it as an envvar
        # BIN_PATH should be a fill path to the directory we want to run as chatops
        if 'BIN_PATH' not in configuration:
            configuration['BIN_PATH'] = os.getenv("CA_BINPATH")
        # Config path is looking for any advanced configs for this plugin
        # Default is BIN_PATH + conf.d/ for ease of user use
        # If the path doesn't exist, we just assume there is no config and set the variable to None
        if 'CONFIG_PATH' not in configuration:
            configuration['CONFIG_PATH'] = os.getenv("CA_CONFPATH", os.path.join(configuration['BIN_PATH'], 'conf.d'))
            # check if the path exists, if not log a message and set path to none
            if not Path(configuration['CONFIG_PATH']).exists():
                self.log.info(f"Config Path {configuration['CONFIG_PATH']} does not exist. Will not load any configs")
                configuration['CONFIG_PATH'] = None
        # get our tmp path. If one isn't configured, make one
        if 'TEMP_PATH' not in configuration:
            configuration['TEMP_PATH'] = os.getenv("CA_TMPPATH", None)
            configuration['TMP_CLEANUP'] = False
        # if TEMP_PATH is None or blank, lets create one
        if configuration['TEMP_PATH'] is None or configuration['TEMP_PATH'] == "":
            configuration['TEMP_PATH'] = self._create_temp_dir()
            # this means we should try to cleanup this tempdir on deactivate
            configuration['TMP_CLEANUP'] = True
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
        return {"BIN_PATH": "/change/me",  # path to the executables we want to setup chatops for
                "CONFIG_PATH": "/change/me",  # path to any advanced config
                "TEMP_PATH": "/change/me",  # path to a writable directory for downloading any executables from config
                "EXCLUSIONS": ["bin1", "bin2"]  # any executables to exclude, just the names of them
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

        # call our method to validate our BIN_PATH. It will also raise ValidationException, and we just re-raise it
        try:
            self._validate_path(configuration['BIN_PATH'])
        except ValidationException as error:
            self.log.exception(str(error))
            raise ValidationException(f"Chatops Anything: Unable to validate BIN_PATH {configuration['BIN_PATH']}. "
                                      f"Check logs for more detailed errors")

        # call our path validation method to validate config path if we have one
        if configuration['CONFIG_PATH'] is not None:
            try:
                self._validate_path(configuration['CONFIG_PATH'])
            except ValidationException as error:
                self.log.exception(str(error))
                raise ValidationException(f"Chatops Anything: Unable to validate CONFIG_PATH "
                                          f"{configuration['CONFIG_PATH']}. Check logs for more detailed errors")

        # call our path validation method to validate the temp path
        try:
            self._validate_path(configuration['TEMP_PATH'], writeable=True)
        except ValidationException as error:
            self.log.error(str(error))
            raise ValidationException(f"Chatops Anything: Unable to validate TEMP_PATH {configuration['TEMP_PATH']}. "
                                      f"Check logs for more detailed errors")

        # TEMP_PATH and BIN_PATH really shouldn't be the same.
        if configuration['BIN_PATH'] == configuration['TEMP_PATH']:
            self.log.info(f"BIN_PATH and TEMP_PATH configured to same dir ({configuration['BIN_PATH']}). "
                          f"This can cause issues. Suggest moving TEMP_PATH to its own directory or leave blank and "
                          f"the plugin will create a tempdir automatically")

        # no reason to explicitly error out here, but we should log some info about BIN_PATH and CONFIG_PATH being the
        # same and how that can cause issues.
        if configuration['BIN_PATH'] == configuration['CONFIG_PATH']:
            self.log.info(f"BIN_PATH and CONFIG_PATH configured to same directory. This can cause issues. "
                          f"Suggest moving config to its own directory")

        # we don't really need to validate EXCLUSIONS. If they dont exist in BIN_PATH, we still will exclude them
        return

    # Helper Functions - these are called by our other methods. they are not chatops commands
    def _load_exec_configs(self, config_files: Iterable[Path]) -> Dict:
        """
        Load all of our config files and download binaries and needed
        Args:
            config_files:

        Returns:

        """
        return {}

    def _run_command(self, executable: Path, args: str, msg: ErrbotMessage) -> None:
        """
        Runs an executable with args from chatops and replies in a thread with the results of the execution
        Args:
            executable (Path): Path to the executable
            args (str): Args from chatops
            msg (ErrbotMessage): Errbot Message Object

        Returns:
            None
        """
        # TODO: Write this for real using delegator.py
        self.log.info(f"Calling {executable} with {args}")
        self.send(msg.to,
                  text=f"Calling {executable} with {args}",
                  in_reply_to=msg)
        return

    def _get_help(self, executable: Path) -> str:
        """
        Returns the help text for executable, either set by config or by running the executable with -h
        Args:
            executable (Path): pathlib.Path object pointing to an executable file

        Returns:
            str: help text
        """
        # TODO: Write this. Should check configs to see if we have help for it or run -h via delegator.py
        return ""

    def _validate_path(self, path: str, writeable: bool = False) -> None:
        """
        Validates the passed in path by checking out a couple of things. We're looking for a basic directory that we can
        read from. If writeable is true, we test if we can write to it.
        Args:
            path (str): Path to validate
            writeable (bool): If true, check if the path is writeable. Defaults to false

        Returns:
            None

        Raises:
            errbot.ValidationException when path does not match our validation conditions
        """
        # use python3 pathlib because its great
        test_path = Path(path)
        # test if path exists
        if not test_path.exists():
            raise ValidationException(f"{path} does not exist on the filesystem")
        # test if the path is a file. We're looking for directories only, not files
        if test_path.is_file():
            raise ValidationException(f"{path} is a file and not a path")
        # check this isnt a fifo
        if test_path.is_fifo():
            raise ValidationException(f"{path} points to a FIFO (or a symbolic link pointing to a FIFO)")
        # check the path isnt a block device
        if test_path.is_block_device():
            raise ValidationException(f"{path} is a block device")
        # check this isnt a char_device
        if test_path.is_char_device():
            raise ValidationException(f"{path} is a character device")
        # check this path isnt a socket
        if test_path.is_socket():
            raise ValidationException(f"{path} is a socket")
        # try an iterdir() to check we have permissions to read from the directory
        try:
            test_path.iterdir().__next__()
        except PermissionError as error:
            self.log.exception(str(error))
            raise ValidationException(f"Unable to read from {path}. Make sure the user errbot is running as has "
                                      f"permissions to read from this directory")
        if writeable:
            # writeperms is write for user, write for group or  write for other
            writeperms = stat.S_IWUSR | stat.S_IWGRP | stat.S_IXWOTH
            st = os.state(path)
            mode = st.st_mode
            if not mode & writeperms:
                raise ValidationException(f"{path} is not writeable. Make sure the user errbot is running as has "
                                          f"permissions to write to this directory")
        return

    @staticmethod
    def _get_all_execs_in_path(path: str) -> Iterable[Path]:
        """
        Gets a list of all executable files in the passed in path
        Args:
            path (str): A file system

        Yields:
            Path to an executable file in path
        """
        # convert our str path to a Pathlib pathn
        path = Path(path)
        # permissions for user executable or group executable or other executable
        executable = stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
        # path.iterdir is like doing ls in the directory
        # https://docs.python.org/3/library/pathlib.html#pathlib.Path.iterdir
        for fs_item in path.iterdir():
            # if we've got a file and not a directory, check if its executable
            if fs_item.is_file():
                # use os.stat to get stat info
                st = os.stat(fs_item)
                # get the file's mode
                mode = st.st_mode
                # compare mode to see if we can execute if, if we can, yield this file
                if mode & executable:
                    yield fs_item

    @staticmethod
    def _get_all_confs_in_path(path: str) -> Iterable[str]:
        """
        Gets a list of all conf files in the passed in path
        Args:
            path (str): A file system path

        Returns:
            Iterable of conf files
        """
        # these are the extensions that we consider valid conf files
        conf_extensions = ['*.ini', '*.yaml', '*.yml', '*.json']
        # chain all the globs into an iterable. this is done lazily so each glob is done as the iterator hits it
        return itertools.chain.from_iterable(glob.iglob(os.path.join(path, extension)) for extension in conf_extensions)

    def _create_temp_dir(self) -> Path:
        """
        Creates a temporary directory for use storing downloaded files

        Returns:
            pathlib.Path - path of the created temp directory
        """
        # gettempdir() should return a platform independent temporary directory. Like /tmp on linux
        # join that with errbot-copsa-ourhash so something like /tmp/errbot-copsa-bf7d10d9e8
        tmp = Path(os.path.join(gettempdir(), f"errbot-copsa-{self.HASH}"))
        # create the directory, creating parents if needed
        tmp.mkdir(parents=True, exist_ok=True)
        self.log.info(f"Created tempdir at {tmp}")
        # return our new temp path
        return tmp

    def _cleanup_tempdir(self, path: str) -> None:
        """
        Uses shutil.rmtree to cleanup our tempdir. Called by deactivate
        Args:
            path (str): Path to cleanup

        Returns:
            None
        """
        # system_temp_path is what our system thinks the temp directory should be
        system_temp_path = Path(gettempdir())
        # convert our path we're being asked to delete into a Path object
        to_delete_path = Path(path)
        # if system_temp_path is in the parents of the path we're looking to delete, that means its a subdirectory.
        # i.e. something like /tmp/path
        if system_temp_path in to_delete_path.parents:
            self.log.info(f"Removing {path}")
            rmtree(path, ignore_errors=True)
        else:
            self.log.error(f"Asked to remove {path} but that's not in {system_temp_path}. "
                           f"Not deleting for fear of deleting files outside of temp!")
