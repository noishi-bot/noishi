from noishi import Context as RawContext
from noishi import pdu, serial, sms, at
from noishi import auto_hot_reload
from noishi import logger as Logger
from noishi.event.sms import SmsReceived
from typing import TYPE_CHECKING
import asyncio

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Main as ExtendContext
    class Context(ExtendContext, RawContext): ...
else:
    Context = RawContext

def main():
    async def _main():
        ctx = Context()
        ctx.add_sub_module(Logger,level=Logger.LogLevel.DEBUG)
        ctx.add_sub_module(pdu)
        ctx.add_sub_module(at)
        ctx.add_sub_module(serial, port="COM6")
        ctx.add_sub_module(sms)
        
        logger = ctx.logger("main")
        @ctx.register_event_handler
        async def sms_received(event: SmsReceived):
            await logger.info(f"收到短信:\n短信中心: {event.sca_number}\n发送者: {event.sender}\n正文: {event.text}\n正文编码类型: {event.text_type}")
        
        auto_hot_reload_list = [serial,pdu,at,sms]
        asyncio.create_task(auto_hot_reload(ctx,auto_hot_reload_list))
        
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    asyncio.run(_main())


if __name__ == "__main__":
    main()
