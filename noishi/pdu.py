from noishi import Context as RawContext
from shua.struct.binary import BinaryStruct
from shua.struct.field import UInt8, BytesField
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Pdu as ExtendContext
    class Context(ExtendContext, RawContext): ...
else:
    Context = RawContext
    
class SCA(BinaryStruct):
    length: UInt8
    type: UInt8
    number: BytesField = BytesField(length=lambda ctx: ctx['length'] - 1)

class TPDU(BinaryStruct):
    first_octet: UInt8
    sender_length: UInt8
    sender_type: UInt8
    sender_number: BytesField = BytesField(length=lambda ctx: (ctx['sender_length'] + 1) // 2)
    pid: UInt8
    dcs: UInt8
    scts: BytesField = BytesField(length=7)
    udl: UInt8
    user_data: BytesField = BytesField(length=lambda ctx: ctx['udl'] * 2 if ctx['dcs'] == 8 else ctx['udl'])

def swap_nibbles(s: str) -> str:
    return ''.join(s[i + 1] + s[i] for i in range(0, len(s), 2))

def decode_number(number_hex: str, length: int) -> str:
    return swap_nibbles(number_hex).rstrip('F')[:length]

def decode_sca(sca_bytes: bytes) -> str:
    if not sca_bytes or sca_bytes[0] == 0:
        return ''
    length, typ = sca_bytes[0], sca_bytes[1]
    number = decode_number(sca_bytes[2:2 + length - 1].hex().upper(), (length - 1) * 2)
    return ('+' + number) if typ == 0x91 else number

def unpack_7bit(data: bytes, length: int) -> bytes:
    septets = []
    carry = 0
    carry_bits = 0

    for b in data:
        current = ((b << carry_bits) & 0x7F) | carry
        septets.append(current)
        carry = b >> (7 - carry_bits)
        carry_bits += 1
        if carry_bits == 7:
            septets.append(carry)
            carry_bits = 0
            carry = 0

    return bytes(septets[:length])

def decode_7bit(data: bytes, length: int) -> str:
    septets = unpack_7bit(data, length)
    import gsm0338 # noqa: F401
    return septets.decode("gsm03.38")

def decode_pdu(pdu_hex: str) -> tuple[str, str, str, str]:
    data = bytes.fromhex(pdu_hex)
    sca_len = data[0]
    sca_number = decode_sca(data[:1 + sca_len])
    tpdu = TPDU.parse(data[1 + sca_len:])
    sender_number = decode_number(tpdu.sender_number.hex().upper(), tpdu.sender_length)
    sender = ('+' + sender_number) if tpdu.sender_type == 0x91 else sender_number

    if tpdu.dcs == 8:
        text_type = "UCS2"
        text = tpdu.user_data.decode('utf-16-be')
    elif tpdu.dcs & 0x0C == 0x00:
        text_type = "GSM7BIT"
        text = decode_7bit(tpdu.user_data, tpdu.udl)
    elif tpdu.dcs & 0x0C == 0x04:
        text = tpdu.user_data.decode('latin-1')
        text_type = "latin-1"
    else:
        text_type = "null"
        text = tpdu.user_data.hex()

    return sca_number, sender, text, text_type

def apply(ctx: Context):
    # TODO: 热重载支持
    sub = ctx.register('pdu')
    
    def _decode_pdu(pdu: str) -> tuple[str, str, str, str]:
        """解码 PDU 格式短信，返回 SCA、发送者、短信文本、短信编码类型"""
        return decode_pdu(pdu)
    
    sub.register('decode',_decode_pdu)
    return sub

inject = ["logger"]
