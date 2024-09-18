"""Module for handling the configuration file."""

from pathlib import Path
from tomlkit import load, dumps


class ConfigHandler:
    """Class for handling configuration file reading and manipulation."""

    def __init__(self) -> None:
        self.configfile = Path("config.toml")
        self.read()

    def read(self):
        with self.configfile.open() as fp:
            self.doc = load(fp)

    def write(self):
        dumps(self.doc)


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
