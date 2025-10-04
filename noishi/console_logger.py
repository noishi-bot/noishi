from noishi import Context, Service
from noishi.logger import LogEvent
import asyncio

class ConsoleLoggerSever(Service):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.ctx = ctx
        # 注册日志事件处理器
        ctx.register_event_handler(self.handle_log_event)
    
    async def handle_log_event(self, event: LogEvent):
        # 直接打印日志事件的字符串表示,懒
        print(str(event))
    
    async def unregister(self):
        #嗯，这不用（
        pass