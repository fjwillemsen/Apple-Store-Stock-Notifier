import socket
import asyncio
from math import floor
from requests.exceptions import ConnectionError

from parameters import username

""" Utilities file, these are functions that are supposed to be very low-level, not requiring either the StoreChecker or Monitor object references """


def reboot_pi():
    """ Reboot the Pi """
    print("Rebooting at the request of the user")
    import subprocess
    subprocess.Popen(['sudo', 'reboot'])

async def send(client, message: str, retry_count=0):
    """ Send a Telegram message """
    try:
        await client.send_message(username, message)
    except ConnectionError as error:
        if retry_count > 5:
            print(f"Retried 5 times, auto-rebooting now...")
            reboot_pi()
        backoff_time = 10
        print(f"ConnectionError on sending Telgram message, waiting {backoff_time} seconds to try again. Error: {error}")
        await asyncio.sleep(backoff_time)
        await send(client, message, retry_count+1)
    
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def past_time_formatter(count, polling_interval_seconds):
    past_seconds = count * polling_interval_seconds
    whole_hours = floor(past_seconds / (60*60))
    whole_minutes = floor(past_seconds / 60) - whole_hours * 60
    remaining_seconds = past_seconds % 60
    txt = ""
    if whole_hours > 0:
        txt += f"{whole_hours} hour{'s' if whole_hours > 1 else ''} "
    if whole_minutes > 0:
        txt += f"{whole_minutes} minute{'s' if whole_minutes > 1 else ''} "
    if remaining_seconds > 0:
        txt += f"{remaining_seconds} second{'s' if remaining_seconds > 1 else ''} "
    txt = txt[:-1]
    return txt