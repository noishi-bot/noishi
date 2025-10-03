from noishi import Context as RawContext
from noishi import pdu, serial, sms, hot_reload
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
        ctx.add_sub_module(serial, port="COM11")
        ctx.add_sub_module(sms)
        
        hot_reload_list = [serial]
        asyncio.create_task(hot_reload.start_hot_reload(ctx,hot_reload_list,asyncio.get_running_loop()))
        
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
            

    asyncio.run(_main())


if __name__ == "__main__":
    main()
