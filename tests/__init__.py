"""Offline test package: any attempt to open a network connection fails loudly."""

import socket
from typing import NoReturn


def _blocked(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("network access is disabled in tests")


socket.socket.connect = _blocked  # type: ignore[method-assign,assignment]
socket.create_connection = _blocked  # type: ignore[assignment]
