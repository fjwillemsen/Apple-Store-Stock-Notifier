"""File containing interface abstract classes."""

from abc import ABC, abstractmethod
from pathlib import Path


class CallbacksAbstract(ABC):
    """An abstract class to provide an interface for callbacks from the monitor to a client."""

    @abstractmethod
    async def on_start(self):
        pass

    @abstractmethod
    async def on_stop(self):
        pass

    @abstractmethod
    async def on_stock_available(self, message):
        pass

    @abstractmethod
    async def on_appointment_available(self, message):
        pass

    @abstractmethod
    async def on_newly_available(self):
        pass

    @abstractmethod
    async def on_auto_report(self, report: str):
        pass

    @abstractmethod
    async def on_proxy_depletion(self, message: str):
        pass

    @abstractmethod
    async def on_long_processing_warning(self, warning: str):
        pass

    @abstractmethod
    async def on_connection_error(self, error: str):
        pass

    @abstractmethod
    async def on_error(self, error: str, logfile_path: Path):
        pass
