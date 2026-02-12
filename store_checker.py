"""Core class for searching stores."""

import time
import logging
from datetime import datetime
from typing import Tuple

import crayons
import minibar
import requests

from http_request_randomizer.requests.proxy.requestProxy import RequestProxy
from http_request_randomizer.requests.errors.ProxyListException import (
    ProxyListException,
)

from interface import CallbacksAbstract
from confighandler import Configuration


class StoreChecker:
    """Class to handle store checking and fetching and processing of stock of apple products."""

    # Base URL is the apple's URL used to make product links and also API
    # calls. Country code is needed only for non-US countries.
    APPLE_BASE_URL = "https://www.apple.com/{0}/"
    # End point for searching for all possible product combinations in the
    # given product family.
    PRODUCT_LOCATOR_URL = "{0}shop/product-locator-meta?family={1}"
    # End point for searching for pickup state of a certain model at a certain
    # location.
    PRODUCT_AVAILABILITY_URL = "{0}shop/retail/pickup-message?pl=true&parts.0={1}&{2}"
    # URL for the store availabile
    STORE_APPOINTMENT_AVAILABILITY_URL = "https://retail-pz.cdn-apple.com/product-zone-prod/availability/{0}/{1}/availability.json"
    # URL for the product buy
    PRODUCT_BUY_URL = "{0}shop/buy-iphone/{1}"

    def __init__(
        self,
        callbacks: CallbacksAbstract,
        configuration: Configuration,
        randomize_proxies=False,
    ):
        """Initialize the configuration for checking store(s) for stock."""

        self.configuration = configuration
        self.stores_list_with_stock = {}
        self.base_url = "https://www.apple.com/"
        self.last_status = "No status available yet, store checker has not completed"
        self.status_list = list()
        self.device_list = list()
        self.callbacks = callbacks

        # set up randomized proxies if specified
        self.randomize_proxies = randomize_proxies
        self.count_randomized_proxy_success = 0
        self.proxy_list_refresh_count = 0
        if self.randomize_proxies:
            self.refresh_proxies()

        # Since the URL only needs country code for non-US countries, switch the URL for country == US.
        if self.configuration.country_code.upper() != "US":
            self.base_url = self.APPLE_BASE_URL.format(self.configuration.country_code)

    def get_last_status(self):
        return self.last_status

    def get_statuslist(self):
        statuslist = "\n".join(self.status_list)
        statuslist = statuslist.replace("✔", "✅")
        statuslist = statuslist.replace("✖", "❌")
        return statuslist

    def refresh_proxies(self):
        """Get a new list of proxies"""
        try:
            print("Assembling a list of proxies to use...\n")
            self.req_proxy = RequestProxy(log_level=logging.CRITICAL)
            self.initial_num_proxies = self.get_num_proxies()
            self.proxy_list_refresh_count += 1
        except ProxyListException as error:
            print(f"Couldn't find any proxies, not using a proxy! \nError: {error}\n")
            self.randomize_proxies = False

    def get_num_proxies(self) -> int:
        """Get the number of proxies in the list"""
        if self.randomize_proxies is True:
            return len(self.req_proxy.get_proxy_list())
        return 0

    async def refresh(self, verbose=True):
        """Refresh information about the stock that is available on the Apple website, returns whether it is available"""
        start_time = time.perf_counter()

        # only look up the devices once, assuming this only needs to happen once per session
        if len(self.device_list) == 0:
            print("Looking up the requested devices...\n")
            self.device_list = await self.find_devices(verbose)
            # Exit if no device was found.
            if not self.device_list:
                print(
                    "{}".format(
                        crayons.red(
                            "✖  No device matching your configuration was found!"
                        )
                    )
                )
                exit(1)
            else:
                if verbose:
                    print(
                        "{} {} {}".format(
                            crayons.green("✔  Found"),
                            len(self.device_list),
                            crayons.green("devices matching your config."),
                        )
                    )
            print("Retrieving stock and appointment information...")

        # Downloading the list of products from the server.
        if verbose:
            print(
                "{}".format(
                    crayons.blue(
                        "➜  Downloading Stock Information for the devices...\n"
                    )
                )
            )

        self.stores_list_with_stock = {}
        for device in minibar.bar(self.device_list) if verbose else self.device_list:
            await self.check_stores_for_device(device)

        # Get all the stores and sort it by the sequence.
        stores = list(self.stores_list_with_stock.values())
        stores.sort(key=lambda k: k["sequence"])

        # Boolean indicating if the stock is available for any of the items
        # requested (used to play the sound)
        stock_available = False

        # Go through the stores and fetch the stock for all the devices/parts
        # in the store and print their status.
        message = ""

        def getlink(device_list, partNumber: str) -> str:
            for device in device_list:
                if device.get("model") == partNumber:
                    return device.get("link")
            return self.base_url

        for store in stores:
            if verbose:
                print(
                    "\n\n{}, {} ({})".format(
                        crayons.green(store.get("storeName")),
                        crayons.green(store.get("city")),
                        crayons.green(store.get("storeId")),
                    )
                )
            message += "\n\n <b>{}, {} ({})</b>\n".format(
                store.get("storeName"), store.get("city"), store.get("storeId")
            )
            for part_id, part in store.get("parts").items():
                partNumber = part.get("partNumber")
                available = (
                    part.get("messageTypes").get("regular").get("storeSelectionEnabled")
                )
                if available:
                    stock_available = True
                storePickupProductTitle = (
                    part.get("messageTypes")
                    .get("regular")
                    .get("storePickupProductTitle")
                )
                partNumber = part.get("partNumber")
                if verbose:
                    print(
                        " - {} {} ({})".format(
                            crayons.green("✔") if available else crayons.red("✖"),
                            (
                                crayons.green(storePickupProductTitle)
                                if available
                                else crayons.red(storePickupProductTitle)
                            ),
                            (
                                crayons.green(partNumber)
                                if available
                                else crayons.red(partNumber)
                            ),
                        )
                    )
                message += "{} {}{}{} ({})\n".format(
                    "✅" if available else "❌",
                    (
                        f'<a href="{getlink(self.device_list, partNumber)}">'
                        if available
                        else ""
                    ),
                    storePickupProductTitle,
                    "</a>" if available else "",
                    partNumber,
                )

        current_datetime = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        processing_time = round(time.perf_counter() - start_time, 3)
        self.last_status = f"<i>Status as of {current_datetime} (took {processing_time} seconds):</i> \n{message}"

        # Play the sound if phone is available.
        if stock_available:
            # immediately send a message!
            await self.callbacks.on_stock_available(message)
            if verbose:
                print(
                    "\n{}".format(crayons.green("Current Status - Stock is Available"))
                )
            else:
                short_status = f"✔ {current_datetime} (in {processing_time} seconds)"
                self.status_list.append(short_status)
                print(crayons.green(short_status))
        elif verbose:
            print("\n{}".format(crayons.red("Current Status - No Stock Available")))
        else:
            short_status = f"✖ {current_datetime} (in {processing_time} seconds)"
            self.status_list.append(short_status)
            print(crayons.red(short_status))
        if verbose:
            print("\n")

        # lookup the appointment slots if the user has this configured
        if not not self.configuration.appointment_stores:
            slots_found, message = await self.get_store_availability()
            if slots_found is True:
                await self.callbacks.on_appointment_available(message)

        return stock_available, current_datetime, processing_time

    async def find_devices(self, verbose=True):
        """Find the required devices based on the configuration."""
        # Store the information about the available devices for the family -
        # title, model, carrier.
        device_list = []
        # Downloading the list of products from the server for the current
        # device family.
        if verbose:
            print("{}".format(crayons.blue("➜  Downloading Models List...")))
        product_locator_response = await self.get_request(
            self.PRODUCT_LOCATOR_URL.format(
                self.base_url, self.configuration.device_family
            )
        )
        if (
            product_locator_response.status_code != 200
            or product_locator_response.json() is None
        ):
            print("----> HERE" + str(device_list))
            return []

        try:
            product_list = (
                product_locator_response.json()
                .get("body")
                .get("productLocatorOverlayData")
                .get("productLocatorMeta")
                .get("products")
            )
            # Take out the product list and extract only the useful
            # information.
            for product in product_list:
                model = product.get("partNumber")
                carrier = product.get("carrierModel")
                # Only add the requested models and requested carriers (device
                # models are partially matched)
                if (
                    any(
                        item in model
                        for item in self.configuration.selected_device_models
                    )
                    or len(self.configuration.selected_device_models) == 0
                ) and (
                    carrier in self.configuration.selected_carriers
                    or len(self.configuration.selected_carriers) == 0
                ):
                    device_list.append(
                        {
                            "title": product.get("productTitle"),
                            "model": model,
                            "carrier": carrier,
                            "link": product.get("productLink"),
                        }
                    )
        except BaseException:
            if verbose:
                print("{}".format(crayons.red("✖  Failed to find the device family")))
            if self.configuration.selected_device_models is not None:
                if verbose:
                    print(
                        "{}".format(
                            crayons.blue("➜  Looking for device models instead...")
                        )
                    )
                for model in self.configuration.selected_device_models:
                    device_list.append({"model": model})
        print(device_list)
        return device_list

    async def check_stores_for_device(self, device, verbose=True):
        """Find all stores that have the device requested available (does not matter if it's in stock or not)."""

        # Make a request per region
        store_list: list[str] = list()
        for region in self.configuration.regions:
            product_availability_response = await self.get_request(
                self.PRODUCT_AVAILABILITY_URL.format(
                    self.base_url, device.get("model"), region
                )
            )
            if verbose:
                print(product_availability_response)
            if (
                product_availability_response.status_code != 200
                or product_availability_response.json() is None
            ):
                print("\n{}".format(crayons.red("Cannot get stores!")))
                return
            store_list.extend(
                product_availability_response.json().get("body").get("stores")
            )

        # Go through all the stores in the list and extract useful information.
        # Group products by store (put the stock for this device in the store's
        # parts attribute)
        for store in store_list:
            current_store = self.stores_list_with_stock.get(store.get("storeNumber"))
            if current_store is None:
                current_store = {
                    "storeId": store.get("storeNumber"),
                    "storeName": store.get("storeName"),
                    "city": store.get("city"),
                    "sequence": store.get("storeListNumber"),
                    "parts": {},
                }
            new_parts = store.get("partsAvailability")
            old_parts = current_store.get("parts")
            old_parts.update(new_parts)
            current_store["parts"] = old_parts

            # If the store is in the list of user's preferred stores, add it to the
            # list to check for stock.
            if (
                store.get("storeNumber") in self.configuration.selected_stores
                or len(self.configuration.selected_stores) == 0
            ):
                self.stores_list_with_stock[store.get("storeNumber")] = current_store

    async def get_store_availability(self) -> Tuple[bool, str]:
        """Get a list of all the stores to check appointment availability, returns the message to send"""
        print(
            "{}".format(
                crayons.blue("➜  Downloading store appointment availability...\n")
            )
        )
        store_availability_list = await self.get_request(
            self.STORE_APPOINTMENT_AVAILABILITY_URL.format(
                datetime.now().strftime("%Y-%m-%d"), datetime.utcnow().strftime("%H")
            )
        )
        message = ""
        slots_found = False
        for store in store_availability_list.json():
            if store.get("storeNumber") in self.configuration.appointment_stores:
                store_number = store.get("storeNumber")
                if store.get("appointmentsAvailable") is True:
                    appointment_datetime = datetime.utcfromtimestamp(
                        int(store.get("firstAvailableAppointment"))
                    ).strftime("%d-%m-%Y %H:%M:%S")
                    message += f"First appointment slot available at {store_number}: {appointment_datetime}\n"
                    print(
                        " - Appointment Slot Available: {} {} ({})".format(
                            crayons.green("✔"),
                            store_number,
                            appointment_datetime,
                        )
                    )
                    slots_found = True
                else:
                    print(" - {} {}".format(crayons.red("✖"), store_number))
        print("{}".format(crayons.blue("\n✔  Done\n")))
        return slots_found, message

    async def get_request(
        self, url: str, proxy_retry_count=0, verbose=True
    ) -> requests.Response:
        if verbose:
            print(url)
        """ Wrapper function to execute a get request, optionally with a randomized proxy """
        max_proxy_attempts = 1
        if self.randomize_proxies is False or proxy_retry_count >= max_proxy_attempts:
            if self.randomize_proxies is True:
                print(
                    crayons.red(
                        f"  randomized proxies failed {max_proxy_attempts} times, falling back to a non-proxied request. If this happens often, consider disabling randomized proxies."
                    )
                )
            return requests.get(url)
        else:
            try:
                response = self.req_proxy.generate_proxied_request(url, req_timeout=30)
                if response is not None and isinstance(response, requests.Response):
                    self.count_randomized_proxy_success += 1
                    return response
                else:
                    time.sleep(3)
                    return await self.get_request(url, proxy_retry_count + 1, verbose)
            except ProxyListException:
                message = f"Proxy list has been depleted, refreshing the proxy list..."
                print(message)
                await self.callbacks.on_proxy_depletion(message)
                self.refresh_proxies()
                return await self.get_request(url)
