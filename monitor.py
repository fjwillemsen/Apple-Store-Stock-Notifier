#!/usr/bin/env python

from __future__ import print_function, unicode_literals

import os
import time
import asyncio
from requests.exceptions import ConnectionError
from copy import deepcopy
from math import ceil
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
# imports for Telegram Notifications
from telethon import TelegramClient, events, types, errors

from utils import send, reboot_pi, get_ip, past_time_formatter
from store_checker import StoreChecker
from parameters import username, api_id, api_hash, bot_token, session_name, polling_interval_seconds, report_after_n_counts, config_path, data_path, log_path, randomize_proxies


# registering the possible user commands
commands_available = {
    'status': 'retrieve the most recent check',
    'liststatus': 'retrieve the statuses over the past report interval',
    'proxystatus': 'retrieve the current proxy status',
    'plotprocessingtime': 'plot the processing time over time',
    'plotavailability': 'plot the availability over time',
    'getdata': 'get the collected data as a CSV file',
    'getlog': 'get the log file as a TXT file',
    'getconfig': 'get the configuration file as a JSON file',
    'setconfig': 'set the configuration file to the attachment (requires reboot)',
    'setpollinginterval': 'set the polling interval in seconds (requires reboot)',
    'setreportinterval': 'set the report interval (requires reboot)',
    'reboot': 'reboot the Pi',
    'terminate': 'terminate the monitor (it can no longer be accessed via Telegram!)',
}
commands_available_txt = "Commands available (use /setcommands in the Botfather chat to set these): \n"
for command, description in commands_available.items():
    commands_available_txt += f"{command} - {description}\n"
print(commands_available_txt)


class Monitor:
    """A class to constantly monitor stock at periodic intervals."""

    def __init__(self):
        """Initializer."""
        # first initialize the Telegram bot
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.session_name = session_name

        # creating a Telegram session and assigning it to a variable client
        client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        client.parse_mode = 'html'
        client.start(bot_token=self.bot_token)

        # set up the dataframe to store data and the data buffer
        if os.path.exists(data_path):
            self.df = pd.read_csv(data_path, index_col=[0])
        else:
            self.df = pd.DataFrame(
                {'availability': pd.Series(dtype='bool'),
                 'datetimestamp': pd.Series(dtype='datetime64[ns]'),
                 'processing_time': pd.Series(dtype='float64')
                 })
        self.data = self.df.to_dict('records')

        # initializing the store checker
        print("Apple Store Monitoring\n")
        self.store_checker = StoreChecker(username, randomize_proxies=randomize_proxies)

        # registering Telegram responses to the requests ((?i) makes it case insensitive)
        # status handler
        @client.on(events.NewMessage(pattern='(?i)/status'))
        async def handler(event):
            status = self.store_checker.get_last_status()
            await event.respond(status)

        # liststatus handler
        @client.on(events.NewMessage(pattern='(?i)/liststatus'))
        async def handler(event):
            statuslist = self.store_checker.get_statuslist()
            await event.respond(f"Overview of all recent statuses: \n{statuslist}")

        # proxystatus handler
        @client.on(events.NewMessage(pattern='(?i)/proxystatus'))
        async def handler(event):
            await event.respond(self.get_proxystatus())

        # termination handler
        @client.on(events.NewMessage(pattern='(?i)/terminate'))
        async def handler(event):
            self.save_df()
            await event.respond("Terminating the monitor... \nTo start the monitor again, reboot.")
            exit(0)

        # reboot handler
        @client.on(events.NewMessage(pattern='(?i)/reboot'))
        async def handler(event):
            self.save_df()
            await event.respond("Rebooting, I'll be back...")
            reboot_pi()

        # getdata handler
        @client.on(events.NewMessage(pattern='(?i)/getdata'))
        async def handler(event):
            self.save_df()
            async with client.action(username, 'document') as action:
                await client.send_file(username, 'data.csv', progress_callback=action.progress, caption="Here's the data file!")
        
        # getlog handler
        @client.on(events.NewMessage(pattern='(?i)/getlog'))
        async def handler(event):
            self.save_df()
            await self.send_log(client)

        # plotprocessingtime handler
        @client.on(events.NewMessage(pattern='(?i)/plotprocessingtime'))
        async def handler(event):
            filepath = self.plot_over_time(
                yaxis="processing_time", ylabel="Processing time in seconds")
            async with client.action(username, 'photo') as action:
                await client.send_file(username, filepath, progress_callback=action.progress, caption="Here's the plot!")

        # plotavailability handler
        @client.on(events.NewMessage(pattern='(?i)/plotavailability'))
        async def handler(event):
            filepath = self.plot_over_time(
                yaxis="availability", ylabel="Available")
            async with client.action(username, 'photo') as action:
                await client.send_file(username, filepath, progress_callback=action.progress, caption="Here's the plot!")

        # getconfig handler
        @client.on(events.NewMessage(pattern='(?i)/getconfig'))
        async def handler(event):
            async with client.action(username, 'document') as action:
                await client.send_file(username, config_path, progress_callback=action.progress, caption="Here's the configuration file!")

        # setconfig handler
        @client.on(events.NewMessage(pattern='(?i)/setconfig'))
        async def handler(event):
            await event.respond(f"Attach a new `{config_path}` in your next message and it will be set! Don't forget to delete data.csv in case something relevant changed.")

        # general handler for all uploaded files
        @client.on(events.NewMessage())
        async def handler(event):
            if event.document is not None:
                # handle new config.json upload
                if event.document.mime_type == 'application/json' and types.DocumentAttributeFilename(config_path) in event.document.attributes:
                    # check if we are in the correct folder before changing anything
                    if os.path.exists("monitor.py"):
                        # first remove the old config.json
                        os.remove(config_path)
                        # then download the new one
                        config = await event.download_media()
                        await event.respond(f"Succesfully set the new {config_path} ({str(config)}). Reboot to apply.")
                    else:
                        await event.respond(f"The current working directory is not the directory of this application. Aborting {config_path} replacement.")
                else:
                    await event.respond(f"If you were trying to set a new {config_path}, make sure the file is named exactly that.")

        # starting the monitoring
        with client:
            try:
                client.loop.run_until_complete(self.start_monitoring(client))
            except KeyboardInterrupt:
                client.loop.run_until_complete(self.stop_monitoring(client))

    async def start_monitoring(self, client):
        """Start monitoring store's stock."""

        # inform the user that monitoring has commenced
        message = f"New monitoring session!\nIP address: {get_ip()}"
        print(message)
        await send(client, message)

        # setup the report counters
        count_connection_errors = 0
        count = 0
        found_availables = list()
        processing_time_list = list([0])

        while True:
            try:
                # get the new data and write to the data and report buffers
                start_time = time.perf_counter()
                availability, datetimestamp, refresh_processing_time = await self.store_checker.refresh(client, verbose=False)
                self.data.append({'availability': availability, 'datetimestamp': datetimestamp,
                                  'processing_time': refresh_processing_time})
                newly_available = availability is True and (not found_availables or found_availables[-1] is False)
                found_availables.append(availability)
                count += 1
                count_connection_errors += 1

                # if we just changed status from unavailable to available, spam the user to notify
                if newly_available:
                    for i in range(10):
                        await send(client, f"AVAILABLE! {i}")
                        await asyncio.sleep(1)

                # generate a report if condition is met
                if count >= report_after_n_counts:

                    # collect the report data
                    count_availables = sum(found_availables)
                    processing_time_list.append(
                        time.perf_counter() - start_time)
                    processing_time_average = round(
                        sum(processing_time_list) / len(processing_time_list), 3)

                    # send and print the report
                    report_message = f"<b>Status Report</b> \nIn the past {past_time_formatter(count, polling_interval_seconds)}, iPhones were available {count_availables} out of {len(found_availables)} times. \nThe average processing time was {processing_time_average} seconds."
                    if randomize_proxies:
                        report_message += f"\nProxy status: {self.get_proxystatus()}"
                    await send(client, report_message)
                    print(report_message)

                    # write the collected data to dataframe and csv
                    self.save_df()

                    # reset the counters for the next report
                    found_availables = list()
                    processing_time_list = list([0])
                    self.store_checker.statuslist = list()
                    count = 0

                # subtract the processing time from the sleep counter for accuracte polling intervals
                processing_time = time.perf_counter() - start_time
                processing_time_list.append(processing_time)
                sleep_time = polling_interval_seconds - processing_time

                # if the processing took much longer than the set interval, crash the process and report
                if processing_time > polling_interval_seconds * 20:
                    raise RuntimeError(
                        f"Processing took more than 20 times longer ({round(processing_time, 3)} seconds) than the set polling interval ({polling_interval_seconds} seconds). To avoid this, look into the cause of the delay (randomized proxies are slow) or increase the interval and reboot.")

                # if the processing took longer than the interval, make up the difference by skipping the next polls
                if processing_time >= polling_interval_seconds:
                    additional_start_time = time.perf_counter()
                    deficit = processing_time - polling_interval_seconds
                    skips = ceil(deficit / polling_interval_seconds)
                    await send(client, f"Processing took longer ({round(processing_time, 3)} seconds) than the set polling interval ({polling_interval_seconds} seconds). \nSkipping {skips} polling{'s' if skips != 1 else ''}. \nIf you get this message often, disable randomized proxies or increase the polling interval and reboot.")
                    count += skips
                    additional_processing_time = time.perf_counter() - additional_start_time
                    sleep_time = (polling_interval_seconds - (deficit % polling_interval_seconds)) - additional_processing_time

                # wait for the next polling
                sleep_time = max(0, sleep_time)
                await asyncio.sleep(sleep_time)

            except errors.rpcerrorlist.AuthKeyDuplicatedError as error:
                print("Duplicate keys, removing the session file and rebooting")
                await send(client, f"Duplicate keys detected, removing the session files and rebooting. \n\nFull error: \n{error}")
                os.remove("bot.session")
                reboot_pi()

            except ConnectionError as error:
                count_connection_errors += 1
                backoff_time = polling_interval_seconds * count_connection_errors
                message = f"Connection error, the server has likely refused the request because of too many attempts. \nTaking a break for {backoff_time} seconds before attempting again. Error message: {error}"
                print(message)
                await send(client, message)
                await asyncio.sleep(backoff_time)

            except BaseException as error:
                print("Something went wrong!")
                await send(client, f"<b>Oops!</b> Something went wrong, the monitor <i>crashed</i>.\n  Reason: {error}")
                await self.send_log(client)
                self.save_df()
                raise error

    async def stop_monitoring(self, client):
        """ Stop the monitoring process """
        print("\nStopping the monitor")
        await send(client, f"This bot is done scouting the shelves, goodbye!")
        self.save_df()

    async def send_log(self, client):
        if os.path.exists(log_path):
            async with client.action(username, 'document') as action:
                await client.send_file(username, log_path, progress_callback=action.progress, caption="Here's the log file!")
        else:
            message = f"Can't send the log file because there isn't one at {log_path}!"
            print(message)
            await send(client, message)

    def save_df(self):
        """ Save the data to a dataframe and to csv file """
        self.df = pd.DataFrame(self.data)
        return self.df.to_csv(data_path)

    def get_proxystatus(self):
        """ Generate a proxy status message """
        if self.store_checker.randomize_proxies is True:
            left = self.store_checker.get_num_proxies()
            initial = self.store_checker.initial_num_proxies
            proxy_list_refresh_count = self.store_checker.proxy_list_refresh_count
            message = f"Proxies were succesful {self.store_checker.count_randomized_proxy_success} times. \nThere are {left} of the initial {initial} proxies left to use. \n{initial-left} proxies have been removed. \nThe proxy list has been assembled {proxy_list_refresh_count} time{'s' if proxy_list_refresh_count != 1 else ''}."
        else:
            if self.randomize_proxies is True:
                message = "Randomized proxies were enabled, but there are no active proxies left. \nNon-proxied requests are used."
            else:
                message = "Randomized proxies are not enabled."
        return message

    def plot_over_time(self, yaxis, ylabel) -> str:
        """ Plot a DF over time, write the plot to disk, return the filepath """
        self.save_df()

        # create a temporary dataframe
        plot_df = deepcopy(self.df)
        plot_df['availability'] = plot_df['availability'].astype(int)
        plot_df = plot_df.set_index('datetimestamp')
        plot_df.plot(y=yaxis)

        # configure the plot
        fig, ax = plt.gcf(), plt.gca()
        fig.set_figheight(6)
        fig.set_figwidth(12)

        # set the labels
        ax.set_xlabel("Time")
        ax.set_ylabel(ylabel)
        if yaxis == 'processing_time':
            # plot the moving average
            ma = plot_df['processing_time'].rolling(
                ceil(report_after_n_counts)).mean()
            plt.plot(ma)
            # limit the y-axis
            ylimmax = min(plot_df[yaxis].max(), polling_interval_seconds)
            ax.set_ylim(0, ylimmax)
        # dates = self.df["datetimestamp"].to_list()
        # dates = [datetime.strptime(x, '%d-%m-%Y %H:%M:%S') for x in dates]
        # ax.set_xticks(dates)
        fig.autofmt_xdate()
        plt.grid()
        plt.tight_layout()

        # return the plot to the user
        plt.savefig("plots/plot.png", dpi=200)
        return "plots/plot.png"


if __name__ == "__main__":
    monitor = Monitor()
