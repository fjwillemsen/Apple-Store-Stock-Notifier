#!/usr/bin/env python
"""Directly executable script for push notifications via ntfy (https://ntfy.sh)."""

import re
import asyncio
from pathlib import Path
import requests
from monitor import Monitor, CallbacksAbstract
from utils import get_ip
from confighandler import ConfigHandler


def html_to_text(message: str) -> str:
    """ntfy does not render HTML, so strip the tags the store checker uses."""
    return re.sub(r"<[^>]+>", "", message).strip()


def first_link(message: str):
    """Get the first link in an HTML message, used as the notification click action."""
    match = re.search(r'href="([^"]+)"', message)
    return match.group(1) if match else None


async def send(url: str, message: str, priority="default", click=None, retry_count=0):
    """Send an ntfy notification"""
    headers = {"Title": "Apple Stock Notifier", "Priority": priority}
    if click is not None:
        headers["Click"] = click
    try:
        response = requests.post(
            url, data=html_to_text(message).encode("utf-8"), headers=headers, timeout=30
        )
        response.raise_for_status()
    except requests.RequestException as error:
        if retry_count >= 5:
            print(f"Retried {retry_count} times, giving up on this notification. Error: {error}")
            return
        backoff_time = 10
        print(
            f"Error on sending ntfy notification, waiting {backoff_time} seconds to try again. Error: {error}"
        )
        await asyncio.sleep(backoff_time)
        await send(url, message, priority, click, retry_count + 1)


# setup callbacks


class Callbacks(CallbacksAbstract):
    def __init__(self, url: str, notification_prefs: dict) -> None:
        self.url = url
        self.notification_prefs = notification_prefs
        super().__init__()

    async def on_start(self):
        if self.notification_prefs.get("on_start", True):
            message = f"New monitoring session!\nIP address: {get_ip()}"
            print(message)
            await send(self.url, message, priority="low")

    async def on_stop(self):
        if self.notification_prefs.get("on_stop", True):
            await send(self.url, "This bot is done scouting the shelves, goodbye!", priority="low")

    async def on_stock_available(self, message):
        if self.notification_prefs.get("on_stock_available", True):
            await send(self.url, message, priority="high", click=first_link(message))

    async def on_appointment_available(self, message):
        if self.notification_prefs.get("on_appointment_available", True):
            await send(self.url, message, priority="high")

    async def on_newly_available(self):
        if self.notification_prefs.get("on_newly_available", True):
            await send(self.url, "AVAILABLE!", priority="urgent")

    async def on_auto_report(self, report: str):
        if self.notification_prefs.get("on_auto_report", True):
            await send(self.url, report, priority="min")

    async def on_proxy_depletion(self, message: str):
        if self.notification_prefs.get("on_proxy_depletion", True):
            await send(self.url, message)

    async def on_long_processing_warning(self, warning: str):
        if self.notification_prefs.get("on_long_processing_warning", True):
            await send(self.url, warning)

    async def on_connection_error(self, error):
        if self.notification_prefs.get("on_connection_error", True):
            await send(self.url, error)

    async def on_error(self, error: str, logfile_path: Path):
        if self.notification_prefs.get("on_error", True):
            await send(
                self.url,
                f"Oops! Something went wrong, the monitor crashed.\n  Reason: {error}",
                priority="high",
            )


def main():
    confighandler = ConfigHandler()
    ntfyconfig = confighandler.get(["ntfy"])
    topic = ntfyconfig.get("topic")
    if not topic:
        raise ValueError("Set [ntfy] topic in config.toml")
    url = f"{ntfyconfig.get('server', 'https://ntfy.sh').rstrip('/')}/{topic}"
    callbacks = Callbacks(url, confighandler.get(["notifications"]) or {})

    # Monitor schedules its config watcher on the current event loop, so set it before creating the Monitor
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    monitor = Monitor(callbacks)
    try:
        loop.run_until_complete(monitor.start_monitoring())
    except KeyboardInterrupt:
        loop.run_until_complete(monitor.stop_monitoring())


if __name__ == "__main__":
    main()
