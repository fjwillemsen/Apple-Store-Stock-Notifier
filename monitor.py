"""Core class for monitoring stores."""

import time
import asyncio
from pathlib import Path
from requests.exceptions import ConnectionError
from copy import deepcopy
from math import ceil
from datetime import datetime
from multiprocessing import Queue

import pandas as pd
import matplotlib.pyplot as plt

from utils import past_time_formatter
from interface import CallbacksAbstract
from store_checker import StoreChecker
from confighandler import ConfigHandler


def next_search_backoff(q: Queue):
    """Update the progress bar via the queue."""
    n = 10
    for i in range(n):
        # Perform some heavy computation
        time.sleep(1)

        # Update the progress bar through the queue
        q.put_nowait(1 - (i / (n - 1)))


class Monitor:
    """A class to constantly monitor stock at periodic intervals and report back via callbacks."""

    def __init__(
        self, callbacks: CallbacksAbstract, path_to_config_file="./config.toml"
    ):
        """Initialization."""
        self.callbacks = callbacks
        self.path_to_config_file = path_to_config_file

        # initialize the ConfigHandler and store checker
        loop = asyncio.get_event_loop()
        init = loop.create_task(self.restart_handler())
        loop.run_until_complete(init)

        # set up the dataframe to store data and the data buffer
        if Path(self.confighandler.get(["general", "data_path"])).exists():
            self.df = pd.read_csv(
                self.confighandler.get(["general", "data_path"]), index_col=[0]
            )
        else:
            self.df = pd.DataFrame(
                {
                    "availability": pd.Series(dtype="bool"),
                    "datetimestamp": pd.Series(dtype="datetime64[ns]"),
                    "processing_time": pd.Series(dtype="float64"),
                }
            )
        self.data = self.df.to_dict("records")
        print("Apple Store Monitoring\n")

    async def restart_handler(self):
        """Callback function to initialize the ConfigHandler and start watching"""
        print("Setting up config handler and store checker for Monitor")
        self.confighandler = ConfigHandler(self.path_to_config_file)
        asyncio.create_task(self.confighandler.watch_changes(self.restart_handler))
        await asyncio.sleep(0.1)  # to let the watcher finish setup
        # initialize the store checker
        self.store_checker = StoreChecker(
            self.callbacks,
            self.confighandler.searchconfig,
            randomize_proxies=self.confighandler.get(["general", "randomize_proxies"]),
        )

    async def start_monitoring(self):
        """Start monitoring store stock."""

        # setup the report counters
        count_connection_errors = 0
        count = 0
        found_availables = list()
        processing_time_list = list([0])

        await self.callbacks.on_start()

        while True:  # TODO find a better way? Check that it isn't hogging resources
            polling_interval_seconds = self.confighandler.get(
                ["general", "polling_interval_seconds"]
            )
            try:
                # get the new data and write to the data and report buffers
                start_time = time.perf_counter()
                availability, datetimestamp, refresh_processing_time = (
                    await self.store_checker.refresh(verbose=False)
                )
                self.data.append(
                    {
                        "availability": availability,
                        "datetimestamp": datetimestamp,
                        "processing_time": refresh_processing_time,
                    }
                )
                newly_available = availability is True and (
                    not found_availables or found_availables[-1] is False
                )
                found_availables.append(availability)
                count += 1
                count_connection_errors += 1

                # if we just changed status from unavailable to available, spam the user to notify
                if newly_available:
                    await self.callbacks.on_newly_available()

                # generate a report if condition is met
                if count >= self.confighandler.get(
                    ["general", "report_after_n_counts"]
                ):

                    # collect the report data
                    count_availables = sum(found_availables)
                    processing_time_list.append(time.perf_counter() - start_time)
                    processing_time_average = round(
                        sum(processing_time_list) / len(processing_time_list), 3
                    )

                    # print the report
                    report_message = f"<b>Status Report</b> \nIn the past {past_time_formatter(count, polling_interval_seconds)}, iPhones were available {count_availables} out of {len(found_availables)} times. \nThe average processing time was {processing_time_average} seconds."
                    if self.confighandler.get(["general", "randomize_proxies"]):
                        report_message += f"\nProxy status: {self.get_proxystatus()}"
                    await self.callbacks.on_auto_report(report_message)
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
                        f"Processing took more than 20 times longer ({round(processing_time, 3)} seconds) than the set polling interval ({polling_interval_seconds} seconds). To avoid this, look into the cause of the delay (randomized proxies are slow) or increase the interval and reboot."
                    )

                # if the processing took longer than the interval, make up the difference by skipping the next polls
                if processing_time >= polling_interval_seconds:
                    additional_start_time = time.perf_counter()
                    deficit = processing_time - polling_interval_seconds
                    skips = ceil(deficit / polling_interval_seconds)
                    await self.callbacks.on_long_processing_warning(
                        f"Processing took longer ({round(processing_time, 3)} seconds) than the set polling interval ({polling_interval_seconds} seconds). \nSkipping {skips} polling{'s' if skips != 1 else ''}. \nIf you get this message often, disable randomized proxies or increase the polling interval and reboot.",
                    )
                    count += skips
                    additional_processing_time = (
                        time.perf_counter() - additional_start_time
                    )
                    sleep_time = (
                        polling_interval_seconds - (deficit % polling_interval_seconds)
                    ) - additional_processing_time

                # wait for the next polling
                sleep_time = max(0, sleep_time)
                await asyncio.sleep(sleep_time)

            except ConnectionError as error:
                count_connection_errors += 1
                backoff_time = polling_interval_seconds * count_connection_errors
                message = f"Connection error, the server has likely refused the request because of too many attempts. \nTaking a break for {backoff_time} seconds before attempting again. Error message: {error}"
                print(message)
                await self.callbacks.on_connection_error(message)
                await asyncio.sleep(backoff_time)

            except BaseException as error:
                print("Something went wrong!")
                await self.callbacks.on_error(error, self.get_logfile_path())
                self.save_df()
                raise error

    def get_logfile_path(self):
        """Get the path to the logfile or None if it does not exist."""
        log_file = Path(self.confighandler.get(["general", "log_path"]))
        return log_file if log_file.exists() else None

    async def stop_monitoring(self):
        """Stop the monitoring process"""
        print("\nStopping the monitor")
        self.save_df()
        await self.callbacks.on_stop()

    def save_df(self):
        """Save the data to a dataframe and to csv file"""
        self.df = pd.DataFrame(self.data)
        return self.df.to_csv(self.confighandler.get(["general", "data_path"]))

    def get_proxystatus(self):
        """Generate a proxy status message"""
        if self.store_checker.randomize_proxies is True:
            left = self.store_checker.get_num_proxies()
            initial = self.store_checker.initial_num_proxies
            proxy_list_refresh_count = self.store_checker.proxy_list_refresh_count
            message = f"Proxies were succesful {self.store_checker.count_randomized_proxy_success} times. \nThere are {left} of the initial {initial} proxies left to use. \n{initial-left} proxies have been removed. \nThe proxy list has been assembled {proxy_list_refresh_count} time{'s' if proxy_list_refresh_count != 1 else ''}."
        else:
            if self.confighandler.get(["general", "randomize_proxies"]) is True:
                message = "Randomized proxies were enabled, but there are no active proxies left. \nNon-proxied requests are used."
            else:
                message = "Randomized proxies are not enabled."
        return message

    def plot_over_time(self, yaxis, ylabel) -> str:
        """Plot a DF over time, write the plot to disk, return the filepath"""
        self.save_df()

        # create a temporary dataframe
        plot_df = deepcopy(self.df)
        plot_df["availability"] = plot_df["availability"].astype(int)
        plot_df = plot_df.set_index("datetimestamp")
        plot_df.plot(y=yaxis)

        # configure the plot
        fig, ax = plt.gcf(), plt.gca()
        fig.set_figheight(6)
        fig.set_figwidth(12)

        # set the labels
        ax.set_xlabel("Time")
        ax.set_ylabel(ylabel)
        if yaxis == "processing_time":
            # plot the moving average
            ma = (
                plot_df["processing_time"]
                .rolling(
                    ceil(self.confighandler.get(["general", "report_after_n_counts"]))
                )
                .mean()
            )
            plt.plot(ma)
            # limit the y-axis
            ylimmax = min(
                plot_df[yaxis].max(),
                self.confighandler.get(["general", "polling_interval_seconds"]),
            )
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
