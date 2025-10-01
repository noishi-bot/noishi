from noishi.ctx import Context as RawContext
from noishi import pdu
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Main_Ctx as ExtendContext
    class Context(ExtendContext, RawContext): ...
else:
    Context = RawContext
        
ctx = Context()

ctx.add_sub_module(pdu)

def main():
    sca_number, sender, text = ctx.pdu.decode("07915892206747F7040D91181154419181F0000852900341933540046D4B8BD5")
    print(f"短信中心:{sca_number}\n发送者:{sender}\n正文:{text}")

if __name__ == "__main__":
    main()