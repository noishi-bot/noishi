from noishi import Context as RawContext
from noishi import pdu, serial, sms
from noishi import auto_hot_reload
from noishi import logger as Logger
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
        ctx.add_sub_module(Logger)
        ctx.add_sub_module(pdu)
        ctx.add_sub_module(serial, port="COM3")
        ctx.add_sub_module(sms)
        
        # 目前pdu不支持热重载,logger无需重载
        auto_hot_reload_list = [serial,sms]
        asyncio.create_task(auto_hot_reload(ctx,auto_hot_reload_list,asyncio.get_running_loop()))
        
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    asyncio.run(_main())


if __name__ == "__main__":
    main()
