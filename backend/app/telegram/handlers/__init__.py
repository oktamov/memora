"""Bot handlers. `register_handlers` wires them onto the Dispatcher."""

from aiogram import Dispatcher

from app.telegram.handlers import capture as capture
from app.telegram.handlers import commands as commands


def register_handlers(dispatcher: Dispatcher) -> None:
    # Commands first: the bare-text handler would otherwise swallow "/start".
    dispatcher.include_router(commands.router)
    dispatcher.include_router(capture.router)


__all__ = ["capture", "commands", "register_handlers"]
