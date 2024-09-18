"""Module for handling the configuration file."""

import asyncio
from pathlib import Path
from tomlkit import load, dumps
from watchfiles import awatch


class ConfigHandler:
    """Class for handling configuration file reading and manipulation."""

    def __init__(self) -> None:
        """Initialization function. Note that you must listen for file changes by calling `watch_changes`."""
        self.configfile_path = Path("config.toml")
        self.read()
        print("Ready!")

    def __get_contents_on_disk(self):
        with self.configfile_path.open() as fp:
            return load(fp)

    def read(self):
        print("read")
        self.doc = self.__get_contents_on_disk()

    def write(self):
        dumps(self.doc)

    def is_outdated(self) -> bool:
        """Checks if the in-memory doc is outdated compared to the on-disk file."""
        return self.__get_contents_on_disk() != self.doc

    async def watch_changes(self, callback_on_external_update=None, auto_update=True):
        """_summary_

        Args:
            callback_on_external_update (Callable, optional): callback function that is called after the configuration has been updated by another instance. Defaults to None.
            auto_update (bool, optional): whether to automatically keep the in-memory doc up to date with the on-disk config. Defaults to True.
        """
        """Watch for changes to the config file, call callback_on_update if"""
        async for _ in awatch(self.configfile_path, poll_delay_ms=1000):
            if self.is_outdated():
                print("outdated")
                if auto_update:
                    self.read()
                if callback_on_external_update is not None:
                    print("calling callback")
                    callback_on_external_update()


if __name__ == "__main__":

    def hi():
        print("hi there!")

    ch = ConfigHandler()
    asyncio.run(ch.watch_changes(hi, auto_update=False))
    print("Ready!")


# content = """[table]
# foo = "bar"  # String
# """
# doc = parse(content)

# # doc is a TOMLDocument instance that holds all the information
# # about the TOML string.
# # It behaves like a standard dictionary.

# assert doc["table"]["foo"] == "bar"

# # The string generated from the document is exactly the same
# # as the original string
# assert dumps(doc) == content
