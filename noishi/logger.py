import datetime
import asyncio
from typing import Optional

from noishi.ctx import Context, Event

class LogEvent(Event):
    def __init__(self, level: str, message: str, timestamp: Optional[datetime.datetime] = None):
        self.level = level
        self.message = message
        self.timestamp = timestamp or datetime.datetime.now()

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {self.level.upper()}: {self.message}"


class Logger:
    def __init__(self, ctx: Context, name: str = "root"):
        self.ctx = ctx
        self.name = name

    async def _log(self, level: str, message: str):
        await self.ctx.send_event(LogEvent(level, f"[{self.name}] {message}"))

    async def debug(self, message: str):
        return asyncio.create_task(self._log("debug", message))

    async def info(self, message: str):
        return asyncio.create_task(self._log("info", message))

    async def warning(self, message: str):
        return asyncio.create_task(self._log("warning", message))

    async def error(self, message: str):
        return asyncio.create_task(self._log("error", message))


def apply(ctx: Context):
    @ctx.register_event_handler
    async def console_logger(event: LogEvent):
        print(str(event))

    def get_logger(name: str = "root") -> Logger:
        return Logger(ctx, name)

    ctx.register("logger", get_logger)
    return ctx

