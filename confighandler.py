"""Module for handling the configuration file, can auto-update and callback on external changes."""

from pathlib import Path
from tomlkit import load, dump
from watchfiles import awatch


class ConfigHandler:
    """Class for handling configuration file reading and manipulation."""

    def __init__(self, path_to_config_file="./config.toml", auto_update=True) -> None:
        """Initialization function. Note that you must listen for file changes by calling `watch_changes`.

        Args:
            path_to_config_file (str, optional): the path to the config file. Defaults to "./config.toml".
            auto_update (bool, optional): whether to automatically keep the in-memory doc up to date with the on-disk config. Defaults to True.
        """
        self.configfile_path = Path(path_to_config_file)
        self.auto_update = auto_update
        assert self.configfile_path.exists()
        self.read()

    def __get_contents_on_disk(self):
        with self.configfile_path.open() as fp:
            return load(fp)

    def read(self):
        """Read the on-disk config to in-memory doc."""
        self.__doc = self.__get_contents_on_disk()
        self.searchconfig = Configuration(self)

    def write(self):
        """Write the in-memory doc to disk. ATTENTION: this can overwrite changes by others if `auto_update` is not used."""
        with self.configfile_path.open("w+") as fp:
            dump(self.__doc, fp)

    def get(self, keys: list[str]):
        """Get a value from the config."""
        val = self.__doc.get(keys.pop(0)) if len(keys) > 0 else self.__doc
        while len(keys) > 0:
            key = keys.pop(0)
            val = val[key]
        return val

    def set(self, keys: list[str], value: any):
        """Set a value in the config. Auto-update config on disk if enabled."""
        dic = self.__doc
        for key in keys[:-1]:
            dic = dic.setdefault(key, {})
        dic[keys[-1]] = value
        if self.auto_update:
            self.write()

    def is_outdated(self) -> bool:
        """Checks if the in-memory doc is outdated compared to the on-disk file."""
        return self.__get_contents_on_disk() != self.__doc

    async def watch_changes(self, callback_on_external_update=None):
        """Watch for changes to the on-disk config file.

        Args:
            callback_on_external_update (Callable, optional): callback function that is called after the configuration has been updated by another instance. Defaults to None.
        """
        async for _ in awatch(self.configfile_path, poll_delay_ms=1000):
            if self.is_outdated():
                if self.auto_update:
                    self.read()
                if callback_on_external_update is not None:
                    callback_on_external_update()


class Configuration:
    """Create a configuration of the device and region to search."""

    def __init__(self, confighandler: ConfigHandler):
        searchconfig = confighandler.get(["search"])
        self.country_code = searchconfig.get("country_code", "us")
        self.device_family = searchconfig.get("device_family")
        self.zip_code = searchconfig.get("zip_code", None)
        self.selected_device_models = searchconfig.get("models", [])
        self.selected_carriers = searchconfig.get("carriers", [])
        self.selected_stores = searchconfig.get("stores", [])
        self.appointment_stores = searchconfig.get("appointment_stores", [])
        self.regions = self.get_regions()

    def get_regions(self) -> list[str]:
        if self.zip_code is not None and len(self.zip_code) > 0:
            return [f"location={self.zip_code}"]
        elif self.selected_stores is not None:
            return [f"store={store}" for store in self.selected_stores]
        raise ValueError("Either zip-code region or specific stores must be selected")
