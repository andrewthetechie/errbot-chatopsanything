from copy import deepcopy
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
from typing import List
from urllib.parse import urlparse

import delegator
from errbot.backends.base import Message as ErrbotMessage
from errbot import BotPlugin
from errbot import Command
from errbot import ValidationException
import json
import requests
import yaml


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
        self.EXECUTABLE_CONFIGS = {}  # typing: Dict
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

        self.log.debug(f"Loaded {len(exec_configs.keys())} configs from file")
        self.BIN_PATH = Path(self.config['BIN_PATH'])
        executables = self._get_all_execs_in_path(self.BIN_PATH)
        self.log.info(f"Found executables at {self.BIN_PATH}")
        self.log.debug(f"{self.config['EXCLUSIONS']} will be excluded from BIN_PATH")
        for executable in executables:
            name = executable.name.lower()
            # add any executables we dont have configs for that aren't in our EXCLUSIONS list
            if name not in exec_configs and name not in self.config['EXCLUSIONS']:
                self.log.debug(f"{executable} has no config file and is not excluded, adding it now")
                exec_configs[name] = dict()
                exec_configs[name]['bin_path'] = executable
                exec_configs[name]['help'] = self._get_help(executable)

        self.log.debug(f"{len(exec_configs.keys())} configs total")
        self.EXECUTABLE_CONFIGS = exec_configs

        # commands is a list of our
        commands = list()
        for command in exec_configs.keys():
            if 'help' not in exec_configs[command]:
                exec_configs[command]['help'] = self._get_help(exec_configs[command]['bin_path'])
            # create a new command for the bot
            self.log.debug(f"Creating new command for {command}")
            commands.append(Command(lambda plugin, msg, args: self._run_command(msg,
                                                                                args),
                            name=command,
                            doc=exec_configs[command]['help']))
        # create a dynamic plugin for all of our executables
        self.create_dynamic_plugin(self.config['PLUGIN_NAME'], tuple(commands))

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
            self.destroy_dynamic_plugin(self.config['PLUGIN_NAME'])
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

        # timeout is an int seconds how long we'll wwait for a command
        if 'TIMEOUT' not in configuration:
            configuration['TIMEOUT'] = os.getenv("COPS_TIMEOUT", 30)

        if 'PLUGIN_NAME' not in configuration:
            configuration['PLUGIN_NAME'] = os.getenv("COPS_PLUGIN_NAME", "Chatops Anything")

        if 'MAX_DOWNLOAD_SIZE' not in configuration:
            configuration['MAX_DOWNLOAD_SIZE'] = os.getenv("COPS_MAX_DL", 3e7)  # approx 30mb

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
                "EXCLUSIONS": ["bin1", "bin2"],  # any executables to exclude, just the names of them
                "PLUGIN_NAME": "Chatops Anything",  # optional, just a name
                "TIMEOUT": 30,  # seconds to wait for a command to execute
                "MAX_DOWNLOAD_SIZE": 3e7  # file size in bytes, default is approx 30mb
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
            config_files [Iterable]: a generator of config files to load

        Returns:
            Dict - any configs from our file system to add
        """
        def merge_two_dicts(x: Dict, y: Dict) -> Dict:
            """
            Given two dicts, x and y, merge them with a deepcopy, y over-writing x
            Args:
                x(Dict): First dict to merge
                y(Dict): Second dict to merge

            Returns:
                Dict - merged copy of the two dicts
            """
            z = deepcopy(x)
            z.update(y)
            return z

        # configs will be an iterable of all of our configs
        loaded_configs = itertools.chain()
        for config_file in config_files:
            self.log.debug(f"Opening {config_file} to read config")
            config_file = Path(config_file)
            if config_file.suffix in ['.yml', '.yaml']:
                this_configs = self._read_yaml_config(config_file)
            elif config_file.suffix == ".json":
                this_configs = self._read_json_config(config_file)
            else:
                self.log.error(f"{config_file} is not a recognized filetype. Skipping it")
                this_configs = []
            loaded_configs = itertools.chain(loaded_configs, this_configs)

        config_dict = dict()
        # step through all of our config objects. Collapse them down into a dict where key = binpath and value is a
        # dict of all our other values from the config
        # if binpath is a url, we stop and do the download here and replace the url with our temporary binpath
        try:
            for loaded_config in loaded_configs:
                # quick validation here
                if 'bin_path' not in loaded_config:
                    if 'url' not in loaded_config:
                        self.log.error(f"Config is invalid. No bin_path or url. Discarding {loaded_config}")
                        continue
                    else:
                        if 'name' not in loaded_config:
                            self.log.error(f"Config provides a url {loaded_config['url']} and no name. "
                                           f"Skipping this config")
                            continue

                        url = urlparse(loaded_config['url'].strip())
                        if url.scheme in ['http', 'https']:
                            try:
                                loaded_config['bin_path'] = self._download_executable(loaded_config['url'],
                                                                                      loaded_config['name'])
                            except ValidationException as exception:
                                self.log.error(f"Error downloading executable at {loaded_config['url']}. {exception}")
                                continue
                            except requests.exceptions.HTTPError as exception:
                                self.log.error(f"Error while downloading executable at {loaded_config['url']}. "
                                               f"{exception}")
                                continue
                        else:
                            self.log.error(f"Config is invalid. URL is not http/s. Discarding {loaded_config}")
                bin_path = Path(loaded_config['bin_path'])
                name = loaded_config.pop('name', None)
                if name is None:
                    name = bin_path.name
                # lower case all the names to canonicalize them
                name = name.lower().strip().replace(" ", "_")
                if name not in config_dict:
                    self.log.debug(f"Adding {name} to our config as a top level key")
                    config_dict[name] = loaded_config
                else:
                    self.log.info(f"{name} already defined. Keys might get overwritten. "
                                  f"Check your configs for duplicates")
                    # merge our configs, overwriting with this new one
                    config_dict[name] = merge_two_dicts(config_dict[name], loaded_config)
        except TypeError as error:
            self.log.error(f"Got a typeerror {error}. Unable to iterate. Are there no loaded configs?")
            config_dict = dict()

        return config_dict

    def _download_executable(self, url: str, filename: str) -> str:
        """
        Downloads an executable over http or https and stores it in our temp path, sets it executable
        Return the path to this executable
        Args:
            url (str): Url to download

        Returns:
            path (str): Path where we've stored the file
        """
        with requests.get(url, allow_redirects=True, stream=True) as response:
            response.raise_for_status()
            content_length = response.headers.get('content-length', None)
            if content_length and float(content_length) > self.config['MAX_DOWNLOAD_SIZE']:
                self.log.error(f"File at {url} is {content_length} in size, greater than MAX_DOWNLOAD_SIZE")
                raise ValidationException(f"File at {url} is {content_length} in size, greater than MAX_DOWNLOAD_SIZE")
            filepath = Path(os.path.join(self.TEMP_PATH, filename))
            with open(filepath, 'wb') as file:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        file.write(chunk)
        self.log.debug(f"Successful download to {filepath}, setting executable")
        st = os.stat(filepath)
        # this is like doing chmod +x
        os.chmod(filepath, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(filepath)

    def _read_yaml_config(self, file: Path) -> List[Dict]:
        """
        Reads a yaml config file from the disk and returns it as a dictionary
        Args:
            file (Path): pathlib.Path object to our file

        Returns:
            List[Dict] - list of config objects from the yaml file
        """
        self.log.debug(f"Opening {file} to read as yaml config")
        with open(file, 'r') as stream:
            try:
                read_data = yaml.load(stream)
            except yaml.YAMLError as exc:
                self.log.error(f"{file} is not a valid yaml config file {str(exc)}")
                return list()

        self.log.debug(f"Read in {file} to {read_data}")
        if type(read_data) != list:
            self.log.error(f"{file} is not a valid config file. Please check the config examples. Your file should "
                           f"contain a list of dictionaries")
            return list()

        return read_data

    def _read_json_config(self, file: Path) -> List[Dict]:
        """
        Reads a json config file from the disk and returns it as a dictionary
        Args:
            file (Path): pathlib.Path object to our file

        Returns:
            List[Dict] - list of config objects from the json file
        """
        self.log.debug(f"Opening {file} to read as json config")
        with open(file, 'r') as stream:
            try:
                read_data = json.load(stream)
            except json.JSONDecodeError as exc:
                self.log.error(f"{file} is not a valid Json config file {str(exc)}")
                return list()

        self.log.debug(f"Read in {file} to {read_data}")
        if type(read_data) != list:
            self.log.error(f"{file} is not a valid config file. Please check the config examples. Your file should "
                           f"contain a list of dictionaries")
            return list()

        return read_data

    def _run_command(self, msg: ErrbotMessage, args: str) -> str:
        """
        Runs an executable with args from chatops and replies in a thread with the results of the execution
        Args:
            args (str): Args from chatops
            msg (ErrbotMessage): Errbot Message Object

        Yields:
            Str - messages to send to the user
        Returns:
            Str - messages to send to the user
        """
        # TODO: PAss along env vars from config
        self.log.debug(f"Message coming in {msg}")
        msg_without_args = msg.body.replace(args, '')
        self.log.debug(f"Message stripped of args {msg_without_args}")
        command_name = msg_without_args.replace(self._bot.prefix, '').lower().strip().replace(" ", "_")
        self.log.debug(f"I think the command being run is {command_name}")
        executable_config = self.EXECUTABLE_CONFIGS[command_name] if command_name in self.EXECUTABLE_CONFIGS else None
        if executable_config is None:
            self.log.error(f"{command_name} not in self.EXECUTABLE_CONFIGS")
            return f"Unable to run your command {command_name} because I am not able to find it in the plugins config."

        self.log.debug(f"Got config {executable_config}")
        try:
            # delegator is awesome and does a bunch of shell escaping for us. Ty Kenneth
            command = delegator.run(f"{executable_config['bin_path']} {args}",
                                    block=False,
                                    timeout=executable_config['timeout'] if 'timeout' in executable_config else
                                    self.config['TIMEOUT'])
        except FileNotFoundError:
            self.log.error(f"Executable not found at {executable_config['bin_path']}")
            return f"Error: Executable not found at {executable_config['bin_path']}"
        except OSError as error:
            self.log.error(f"Executable at {executable_config['bin_path']} threw an os error {error}")
            return f"Error: Error received when running your command.\n{error}"

        self.log.info(f"{executable_config['bin_path']} running with PID {command.pid}")

        yield f"Started your command with PID {command.pid}"
        command.block()

        yield command.out()
        yield f"Command RC: {command.return_code}"

    def _get_help(self, executable: Path) -> str:
        """
        Returns the help text for executable, either set by config or by running the executable with --help
        Args:
            executable (Path): pathlib.Path object pointing to an executable file

        Returns:
            str: help text
        """
        try:
            command = delegator.run(f"{executable} --help",
                                    block=False,
                                    timeout=self.config['TIMEOUT'])
        except FileNotFoundError:
            self.log.error(f"Executable not found at {executable}")
            return "Error: Executable not found"
        except OSError as error:
            self.log.error(f"OS Error encountered for {executable}. {error}")
            return f"Error: {error}"

        command.block()
        return command.out

    def _validate_path(self, path: str, writeable: bool = False) -> bool:
        """
        Validates the passed in path by checking out a couple of things. We're looking for a basic directory that we can
        read from. If writeable is true, we test if we can write to it.
        Args:
            path (str): Path to validate
            writeable (bool): If true, check if the path is writeable. Defaults to false

        Returns:
            True if path is valid

        Raises:
            errbot.ValidationException when path does not match our validation conditions
        """
        # use python3 pathlib because its great
        test_path = Path(path)
        self.log.debug(f"Validating {test_path}")
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
        except StopIteration as stoperror:
            # an empty dir doesnt mean we cant read from it
            pass
        except PermissionError as error:
            self.log.exception(str(error))
            raise ValidationException(f"Unable to read from {path}. Make sure the user errbot is running as has "
                                      f"permissions to read from this directory")
        if writeable:
            if not os.access(test_path, os.W_OK):
                raise ValidationException(f"{path} is not writeable")
        return True

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
        conf_extensions = ['*.yaml', '*.yml', '*.json']
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
