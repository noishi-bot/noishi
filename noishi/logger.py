import datetime
from typing import Optional, cast
from enum import Enum
import weakref

from noishi import Context, Event

class LogLevel(Enum):
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4

    def __str__(self):
        return self.name

class LogEvent(Event):
    def __init__(self, level: LogLevel | str, message: str, timestamp: Optional[datetime.datetime] = None):
        self.level = level
        self.message = message
        self.timestamp = timestamp or datetime.datetime.now()

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {self.level}: {self.message}"

class Logger:
    def __init__(self, ctx: Context, name: str = "root"):
        self.ctx = cast(Context, weakref.proxy(ctx))
        self.name = name

    async def _log(self, level: LogLevel | str, message: str):
        await self.ctx.send_event(LogEvent(level, f"[{self.name}] {message}"))

    async def debug(self, message: str):
        return await self._log(LogLevel.DEBUG, message)

    async def info(self, message: str):
        return await self._log(LogLevel.INFO, message)

    async def warning(self, message: str):
        return await self._log(LogLevel.WARNING, message)

    async def error(self, message: str):
        return await self._log(LogLevel.ERROR, message)

def apply(ctx: Context, level: LogLevel = LogLevel.DEBUG):
    @ctx.register_event_handler
    async def console_logger(event: LogEvent):
        if isinstance(event.level, LogLevel) and event.level.value < level.value:
            return
        colors = {
            LogLevel.DEBUG: "\033[94m",
            LogLevel.INFO: "\033[92m",
            LogLevel.WARNING: "\033[93m",
            LogLevel.ERROR: "\033[91m",
        }
        reset = "\033[0m"
        color = colors.get(event.level, "\033[0m")
        print(f"{color}{str(event)}{reset}")

    def get_logger(name: str = "root") -> Logger:
        return Logger(ctx, name)

    ctx.register("logger", get_logger)
    return ctx
