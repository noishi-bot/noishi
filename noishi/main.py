from noishi.ctx import Context as RawContext
from noishi import pdu
from noishi import logger as Logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Main as ExtendContext
    class Context(ExtendContext, RawContext): ...
else:
    Context = RawContext
        
def main():
    import asyncio
    async def _main():
        ctx = Context()
        ctx.add_sub_module(Logger)
        ctx.add_sub_module(pdu)
        logger = ctx.logger("main")
        sca_number, sender, text = await ctx.pdu.decode("07915892206747F7040D91181154419181F0000852900341933540046D4B8BD5")
        await logger.info(f"\n短信中心:{sca_number}\n发送者:{sender}\n正文:{text}")
        await asyncio.sleep(1)
    asyncio.run(_main())


if __name__ == "__main__":
    main()