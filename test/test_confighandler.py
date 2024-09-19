from confighandler import ConfigHandler
import pytest
import asyncio
import nest_asyncio

nest_asyncio.apply()

CONFIGFILE_PATH = "./test/config.toml"


def test_read():
    """Test whether the confighandler correctly reads from disk."""
    ch = ConfigHandler(CONFIGFILE_PATH)
    assert ch.get(["search", "device_family"]) == "iphone_16_pro"
    assert len(ch.get(["search", "stores"])) == 2


def test_write():
    """Test whether the confighandler correctly writes to disk."""
    ch = ConfigHandler(CONFIGFILE_PATH)
    ch_new = ConfigHandler(CONFIGFILE_PATH)
    ch_new.set(["search", "device_family"], "iphone_15_pro")
    assert ch.get(["search", "device_family"]) == "iphone_16_pro"
    assert ch_new.get(["search", "device_family"]) == "iphone_15_pro"
    assert ch.get([]) != ch_new.get([])
    ch_newest = ConfigHandler(CONFIGFILE_PATH)
    ch_newest.set(["search", "device_family"], "iphone_16_pro")
    assert ch_newest.get(["search", "device_family"]) == "iphone_16_pro"
    assert ch.get([]) == ch_newest.get([])


@pytest.mark.asyncio
async def test_watch_changes_callback():
    """Test whether the confighandler is able to watch for on-disk changes."""

    def callbackfn():
        raise TabError

    ch = ConfigHandler(CONFIGFILE_PATH)
    ch_new = ConfigHandler(CONFIGFILE_PATH)
    # check that the callback works by raising an exception
    with pytest.raises(TabError):
        task = asyncio.create_task(ch.watch_changes(callbackfn))
        await asyncio.sleep(0.5)  # just to make sure the file watcher is setup
        ch_new.set(["search", "device_family"], "iphone_15_pro")
        await task  # can be done because we know callbacks raise an exception, otherwise use e.g. await asyncio.sleep(3)

    # check that the original confighandler now has the new data
    assert ch.get(["search", "device_family"]) == "iphone_15_pro"
    # restore to original for next test
    ch_new.set(["search", "device_family"], "iphone_16_pro")
