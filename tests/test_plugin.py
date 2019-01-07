import os
from pathlib import Path
import random
import shutil
import stat
import string
from tempfile import gettempdir

from errbot import ValidationException
import pytest
import responses
from requests.exceptions import HTTPError

pytest_plugins = ["errbot.backends.test"]

extra_plugin_dir = "."

TEST_PATH = Path(__file__)


def copytree(src, dst, symlinks=False, ignore=None):
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copytree(s, d, symlinks, ignore)
        else:
            if not os.path.exists(d) or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                shutil.copy2(s, d)


def test_temp_dir(testbot):
    """
    Tests we can create a tempdir and destroy it properly if needed

    """
    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    temp_dir = plugin._create_temp_dir()
    # system_temp_path is what our system thinks the temp directory should be
    system_temp_path = Path(gettempdir())
    # convert our path we've gotten to a Path object
    temp_path = Path(temp_dir)
    assert system_temp_path in temp_path.parents
    assert temp_path.is_dir()
    assert os.access(temp_path, os.W_OK)

    # lets test we can clean the path up
    plugin._cleanup_tempdir(temp_path)
    assert not temp_path.is_dir()


def test_get_all_confs_in_path(testbot):
    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    conf_path = os.path.join(TEST_PATH.parent, "test_bin/conf.d")
    confs = list(plugin._get_all_confs_in_path(conf_path))
    assert len(confs) == 4
    expected_conf_paths = [os.path.join(TEST_PATH.parent, f"test_bin/conf.d/{conf_name}") for conf_name in
                           ['test-conf1.yml', 'test-conf2.yaml', 'test-conf3.json']]
    for expected_conf in expected_conf_paths:
        assert expected_conf in confs

    assert os.path.join(TEST_PATH.parent, "test_bin/conf.d/test-random-file.txt") not in confs


def test_get_all_execs_in_path(testbot):
    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    temp_dir = plugin.config['TEMP_PATH']
    test_bin_path = os.path.join(TEST_PATH.parent, "test_bin")
    copytree(test_bin_path, temp_dir)
    for exec_file in ['test_exec', 'argstest']:
        filepath = os.path.join(temp_dir, exec_file)
        st = os.stat(filepath)
        # this is like doing chmod +x
        os.chmod(filepath, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    for non_exec_file in ['test_file.txt', 'test_noexec']:
        filepath = os.path.join(temp_dir, non_exec_file)
        with open(filepath, 'w') as file:
            file.write("")

    execs = list(plugin._get_all_execs_in_path(temp_dir))
    assert len(execs) == 2
    expected_execs = [os.path.join(temp_dir, exec_name) for exec_name in ['argstest', 'test_exec']]
    unexpected_execs = [os.path.join(temp_dir, file_name) for file_name in ['test_file.txt', 'test_noexec']]
    for expected_exec in expected_execs:
        assert Path(expected_exec) in execs

    for unexpected_exec in unexpected_execs:
        assert Path(unexpected_exec) not in execs


def test_validate_path(testbot):
    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    temp_dir = plugin._create_temp_dir()
    bin_path = plugin.config['BIN_PATH']

    assert plugin._validate_path(bin_path)
    assert plugin._validate_path(temp_dir, writeable=True)
    # cleanup our tempdir
    plugin._cleanup_tempdir(temp_dir)

    random_root = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    random_subdir = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    non_existant = os.path.join(random_root, random_subdir)
    with pytest.raises(ValidationException):
        plugin._validate_path(non_existant)

    # TODO: Test unwriteable directory to make sure it properly errors.


def test_read_yaml_config(testbot):
    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    conf_path = os.path.join(TEST_PATH.parent, "test_bin/conf.d/test-conf1.yml")
    loaded_conf = plugin._read_yaml_config(conf_path)
    assert len(loaded_conf) == 1
    assert type(loaded_conf) == list
    assert type(loaded_conf[0]) == dict
    assert loaded_conf[0]['bin_path'] == "/bin/ls"
    assert loaded_conf[0]['name'] == "testls"
    assert loaded_conf[0]['timeout'] == 60
    assert loaded_conf[0]['help'] == "Help text"
    assert type(loaded_conf[0]['env_vars']) == dict
    assert loaded_conf[0]['env_vars']['var_one'] == 1
    assert loaded_conf[0]['env_vars']['var_two'] == 2

    bad_conf_path = os.path.join(TEST_PATH.parent, "test_bin/conf.d/test-confbad.yaml")
    bad_conf = plugin._read_yaml_config(bad_conf_path)
    assert type(bad_conf) == list
    assert len(bad_conf) == 0

    json_conf_path = os.path.join(TEST_PATH.parent, "test_bin/conf.d/test-conf3.json")
    json_conf = plugin._read_yaml_config(json_conf_path)
    assert type(json_conf) == list
    assert len(json_conf) == 0


def test_read_json_config(testbot):
    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    conf_path = os.path.join(TEST_PATH.parent, "test_bin/conf.d/test-conf3.json")
    loaded_conf = plugin._read_json_config(conf_path)
    assert len(loaded_conf) == 1
    assert type(loaded_conf) == list
    assert type(loaded_conf[0]) == dict
    assert loaded_conf[0]['bin_path'] == "/bin/ls"
    assert loaded_conf[0]['name'] == "testlsjson"
    assert loaded_conf[0]['timeout'] == 91
    assert 'help' not in loaded_conf[0]
    assert type(loaded_conf[0]['env_vars']) == dict
    assert loaded_conf[0]['env_vars']['key'] == "value"
    assert loaded_conf[0]['env_vars']['key2'] == "value2"

    bad_conf_path = os.path.join(TEST_PATH.parent, "test_bin/conf.d/test-confbad.yaml")
    bad_conf = plugin._read_json_config(bad_conf_path)
    assert type(bad_conf) == list
    assert len(bad_conf) == 0

    yaml_conf_path = os.path.join(TEST_PATH.parent, "test_bin/conf.d/test-conf1.yml")
    yaml_conf = plugin._read_json_config(yaml_conf_path)
    assert type(yaml_conf) == list
    assert len(yaml_conf) == 0


@responses.activate
def test_download_executable(testbot):
    responses.add(responses.GET, "https://fakeurl.fakesite.com/fakefile", status=200, body="file")
    responses.add(responses.GET, "https://fakeurl.fakesite.com/fakefile2", status=404)

    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    temp_dir = plugin._create_temp_dir()
    file_path = plugin._download_executable("https://fakeurl.fakesite.com/fakefile", "testfile")
    with open(file_path, 'r') as file:
        lines = file.readlines()
    assert len(lines) == 1
    assert lines[0] == "file"

    with pytest.raises(HTTPError):
        plugin._download_executable("https://fakeurl.fakesite.com/fakefile2", "testfile")


@responses.activate
def test_load_exec_configs(testbot, mocker):
    responses.add(responses.GET, "https://fakeurl.fakesite.com/fakefile", status=200, body="file")
    plugin = testbot.bot.plugin_manager.get_plugin_obj_by_name('ChatOpsAnything')
    mocker.patch.object(plugin, "_download_executable")
    plugin._download_executable.return_value = "/tmp/fake/executable"

    conf_files = [Path(os.path.join(TEST_PATH.parent, f"test_bin2/conf.d/{filename}")) for filename in
                  ['test-conf1.yml', 'test-conf2.yaml', 'test-conf3.json']]

    loaded_configs = plugin._load_exec_configs(conf_files)
    assert type(loaded_configs) == dict
    assert len(loaded_configs.keys()) == 5

    for name in ['testls', 'testdl', 'file', 'testoverwrite', 'testlsjson']:
        assert name in loaded_configs
        assert 'bin_path' in loaded_configs[name]

    # comes from test_bin2/conf.d/test-conf1.yml
    assert loaded_configs['testls']['bin_path'] == "/bin/ls"
    assert loaded_configs['testls']['help'] == "Help text"
    assert loaded_configs['testls']['timeout'] == 60
    assert loaded_configs['testls']['env_vars']['var_one'] == 1
    assert loaded_configs['testls']['env_vars']['var_two'] == 2

    # comes from test_bin2/conf.d/test-conf1.yml
    # _download_executable is mocked out, so our bin_path is /tmp/fake/executable
    assert loaded_configs['testdl']['bin_path'] == "/tmp/fake/executable"
    assert "timeout" not in loaded_configs['testdl']
    assert "help" not in loaded_configs['testdl']
    assert "env_vars" not in loaded_configs['testdl']

    # comes from test_bin2/conf.d/test-conf1.yaml
    # tests that we can get a name from an appropriate path
    assert loaded_configs['file']['bin_path'] == "/bin/file"
    assert loaded_configs['file']['timeout'] == 11

    # comes from test_bin2/conf.d/test-conf1.yaml
    # is overwritten/added to in test_bin/conf.d/test-conf3.json
    assert loaded_configs['testoverwrite']['bin_path'] == "/bin/dd"
    assert loaded_configs['testoverwrite']['help'] == "This is help from the json file"

    # comes from test_bin2/conf.d/test-conf3.json
    assert loaded_configs['testlsjson']['bin_path'] == "/bin/ls"
    assert loaded_configs['testlsjson']['env_vars']['key'] == "value"
    assert loaded_configs['testlsjson']['env_vars']['key2'] == "value2"
    assert loaded_configs['testlsjson']['timeout'] == 91
