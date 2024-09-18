""" Utilities file, these are functions that are supposed to be very low-level, not requiring either the StoreChecker or Monitor object references """

import socket
from math import floor


def reboot_pi():
    """Reboot the Pi"""
    print("Rebooting at the request of the user")
    import subprocess

    subprocess.Popen(["sudo", "reboot"])


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP


def past_time_formatter(count, polling_interval_seconds):
    past_seconds = count * polling_interval_seconds
    whole_hours = floor(past_seconds / (60 * 60))
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
