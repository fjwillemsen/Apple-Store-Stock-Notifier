#!/usr/bin/env python
"""Directly executable script for notifications and remote interaction via a Telegram bot."""

import os
import asyncio
from pathlib import Path
from requests.exceptions import ConnectionError as RequestConnectionError
from telethon import TelegramClient, events, types, errors
from parameters import api_id, api_hash, bot_token, session_name, config_path, username
from utils import reboot_pi, get_ip
from monitor import Monitor, CallbacksAbstract


async def send(client, message: str, retry_count=0):
    """Send a Telegram message"""
    try:
        await client.send_message(username, message)
    except RequestConnectionError as error:
        if retry_count > 5:
            print(f"Retried 5 times, auto-rebooting now...")
            reboot_pi()
        backoff_time = 10
        print(
            f"ConnectionError on sending Telgram message, waiting {backoff_time} seconds to try again. Error: {error}"
        )
        await asyncio.sleep(backoff_time)
        await send(client, message, retry_count + 1)


# setup callbacks
class Callbacks(CallbacksAbstract):
    def __init__(self, client) -> None:
        self.client = client
        super().__init__()

    async def on_start(self):
        pass

    async def on_stop(self):
        await send(self.client, "This bot is done scouting the shelves, goodbye!")

    async def on_error(self, error: str, logfile_path: Path):
        await send(
            self.client,
            f"<b>Oops!</b> Something went wrong, the monitor <i>crashed</i>.\n  Reason: {error}",
        )
        await self.send_logfile(logfile_path)

    async def on_newly_available(self):
        for i in range(3):
            await send(self.client, f"AVAILABLE! {i}")
            await asyncio.sleep(1)

    async def on_auto_report(self, report: str):
        await send(self.client, report)

    async def on_long_processing_warning(self, warning: str):
        await send(self.client, warning)

    async def on_connection_error(self, error):
        await send(self.client, error)

    async def send_logfile(self, logfile_path):
        if logfile_path is not None:
            async with self.client.action(username, "document") as action:
                await self.client.send_file(
                    username,
                    logfile_path,
                    progress_callback=action.progress,
                    caption="Here's the log file!",
                )
        else:
            await send(
                self.client,
                f"Can't send the log file because there isn't one at {logfile_path}!",
            )


class TelegramConnection:
    """Class for sending notifications and receiving commands via a Telegram bot."""

    async def __init__(self) -> None:
        # first initialize the Telegram bot
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.session_name = session_name

        # creating a Telegram session and assigning it to a variable client
        client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        client.parse_mode = "html"
        client.start(bot_token=self.bot_token)

        # registering the possible user commands
        commands_available = {
            "status": "retrieve the most recent check",
            "liststatus": "retrieve the statuses over the past report interval",
            "proxystatus": "retrieve the current proxy status",
            "plotprocessingtime": "plot the processing time over time",
            "plotavailability": "plot the availability over time",
            "getdata": "get the collected data as a CSV file",
            "getlog": "get the log file as a TXT file",
            "getconfig": "get the configuration file as a JSON file",
            "setconfig": "set the configuration file to the attachment (requires reboot)",
            "setpollinginterval": "set the polling interval in seconds (requires reboot)",
            "setreportinterval": "set the report interval (requires reboot)",
            "reboot": "reboot the Pi",
            "terminate": "terminate the monitor (it can no longer be accessed via Telegram!)",
        }
        commands_available_txt = "Commands available (use /setcommands in the Botfather chat to set these): \n"
        for command, description in commands_available.items():
            commands_available_txt += f"{command} - {description}\n"
        print(commands_available_txt)

        # set up the monitor
        callbacks = Callbacks(client)
        self.monitor = Monitor(callbacks)

        # start the monitoring
        with client:
            try:
                # inform the user that monitoring has commenced
                message = f"New monitoring session!\nIP address: {get_ip()}"
                print(message)
                await send(client, message)
                client.loop.run_until_complete(self.monitor.start_monitoring(client))
            except KeyboardInterrupt:
                client.loop.run_until_complete(self.monitor.stop_monitoring(client))
            except errors.rpcerrorlist.AuthKeyDuplicatedError as error:
                print("Duplicate keys, removing the session file and rebooting")
                await send(
                    client,
                    f"Duplicate keys detected, removing the session files and rebooting. \n\nFull error: \n{error}",
                )
                os.remove("bot.session")
                reboot_pi()

        # registering Telegram responses to the requests ((?i) makes it case insensitive)
        # status handler
        @client.on(events.NewMessage(pattern="(?i)/status"))
        async def handler(event):
            status = self.monitor.store_checker.get_last_status()
            await event.respond(status)

        # liststatus handler
        @client.on(events.NewMessage(pattern="(?i)/liststatus"))
        async def handler(event):
            statuslist = self.monitor.store_checker.get_statuslist()
            await event.respond(f"Overview of all recent statuses: \n{statuslist}")

        # proxystatus handler
        @client.on(events.NewMessage(pattern="(?i)/proxystatus"))
        async def handler(event):
            await event.respond(self.monitor.get_proxystatus())

        # termination handler
        @client.on(events.NewMessage(pattern="(?i)/terminate"))
        async def handler(event):
            self.monitor.save_df()
            await event.respond(
                "Terminating the monitor... \nTo start the monitor again, reboot."
            )
            exit(0)

        # reboot handler
        @client.on(events.NewMessage(pattern="(?i)/reboot"))
        async def handler(event):
            self.monitor.save_df()
            await event.respond("Rebooting, I'll be back...")
            reboot_pi()

        # getdata handler
        @client.on(events.NewMessage(pattern="(?i)/getdata"))
        async def handler(event):
            self.monitor.save_df()
            async with client.action(username, "document") as action:
                await client.send_file(
                    username,
                    "data.csv",
                    progress_callback=action.progress,
                    caption="Here's the data file!",
                )

        # getlog handler
        @client.on(events.NewMessage(pattern="(?i)/getlog"))
        async def handler(event):
            self.monitor.save_df()
            callbacks.send_logfile(self.monitor.get_logfile_path())

        # plotprocessingtime handler
        @client.on(events.NewMessage(pattern="(?i)/plotprocessingtime"))
        async def handler(event):
            filepath = self.monitor.plot_over_time(
                yaxis="processing_time", ylabel="Processing time in seconds"
            )
            async with client.action(username, "photo") as action:
                await client.send_file(
                    username,
                    filepath,
                    progress_callback=action.progress,
                    caption="Here's the plot!",
                )

        # plotavailability handler
        @client.on(events.NewMessage(pattern="(?i)/plotavailability"))
        async def handler(event):
            filepath = self.monitor.plot_over_time(
                yaxis="availability", ylabel="Available"
            )
            async with client.action(username, "photo") as action:
                await client.send_file(
                    username,
                    filepath,
                    progress_callback=action.progress,
                    caption="Here's the plot!",
                )

        # getconfig handler
        @client.on(events.NewMessage(pattern="(?i)/getconfig"))
        async def handler(event):
            async with client.action(username, "document") as action:
                await client.send_file(
                    username,
                    config_path,
                    progress_callback=action.progress,
                    caption="Here's the configuration file!",
                )

        # setconfig handler
        @client.on(events.NewMessage(pattern="(?i)/setconfig"))
        async def handler(event):
            await event.respond(
                f"Attach a new `{config_path}` in your next message and it will be set! Don't forget to delete data.csv in case something relevant changed."
            )

        # general handler for all uploaded files
        @client.on(events.NewMessage())
        async def handler(event):
            if event.document is not None:
                # handle new config.json upload
                if (
                    event.document.mime_type == "application/json"
                    and types.DocumentAttributeFilename(config_path)
                    in event.document.attributes
                ):
                    # check if we are in the correct folder before changing anything
                    if os.path.exists("monitor.py"):
                        # first remove the old config.json
                        os.remove(config_path)
                        # then download the new one
                        config = await event.download_media()
                        await event.respond(
                            f"Succesfully set the new {config_path} ({str(config)}). Reboot to apply."
                        )
                    else:
                        await event.respond(
                            f"The current working directory is not the directory of this application. Aborting {config_path} replacement."
                        )
                else:
                    await event.respond(
                        f"If you were trying to set a new {config_path}, make sure the file is named exactly that."
                    )
