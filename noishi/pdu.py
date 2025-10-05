from noishi import Context as RawContext
from noishi import logger as Logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Pdu as ExtendContext
    class Context(ExtendContext, RawContext): ...
else:
    Context = RawContext

GSM_7BIT_TABLE: tuple[str, ...] = (
    '@', '£', '$', '¥', 'è', 'é', 'ù', 'ì', 'ò', 'Ç', '\n', 'Ø', 'ø', '\r', 'Å', 'å',
    'Δ', '_', 'Φ', 'Γ', 'Λ', 'Ω', 'Π', 'Ψ', 'Σ', 'Θ', 'Ξ', '€', 'Æ', 'æ', 'ß', 'É',
    ' ', '!', '"', '#', '¤', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/',
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ':', ';', '<', '=', '>', '?',
    '¡', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O',
    'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'Ä', 'Ö', 'Ñ', 'Ü', '§',
    '¿', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o',
    'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', 'ä', 'ö', 'ñ', 'ü', 'à'
)

def swap_nibbles(s: str) -> str:
    """交换十六进制字符串中的半字节"""
    return ''.join([s[i+1]+s[i] for i in range(0, len(s), 2)])

def decode_number(number: str, length: int) -> str:
    """解码电话号码（半字节交换 + 截断长度）"""
    if number.endswith('F') or number.endswith('f'):
        number = number[:-1]
    swapped: str = swap_nibbles(number)
    return swapped[:length]

def decode_sca(sca_hex: str, sca_length_octets: int) -> str:
    """解码短信服务中心号码"""
    if sca_length_octets == 0:
        return ''
    sca_type: str = sca_hex[0:2]
    number_hex: str = sca_hex[2:]
    digits_count: int = (sca_length_octets - 1) * 2
    number: str = decode_number(number_hex, digits_count)
    number = number.rstrip('F')
    if sca_type.lower() == '91':
        return '+' + number
    return number

def decode_7bit(user_data_hex: str, length: int) -> str:
    data = bytearray.fromhex(user_data_hex)
    result = []

    for i in range(length):
        byte_index = (i * 7) // 8
        shift = (i * 7) % 8
        septet = (data[byte_index] >> shift) | ((data[byte_index + 1] << (8 - shift)) & 0x7F if shift > 1 else 0)
        septet &= 0x7F
        result.append(GSM_7BIT_TABLE[septet] if septet < len(GSM_7BIT_TABLE) else '?')
    
    return ''.join(result)

async def decode_pdu(logger: Logger.Logger,pdu: str) -> tuple[str, str, str]:
    """解码 PDU 格式短信，返回 SCA、发送者和短信文本"""
    sca_length: int = int(pdu[0:2], 16)
    sca_end: int = 2 + sca_length*2
    sca: str = pdu[2:sca_end]
    sca_number: str = decode_sca(sca, sca_length)

    tpdu: str = pdu[sca_end:]

    sender_length: int = int(tpdu[2:4], 16)
    sender_type: str = tpdu[4:6]
    sender_number: str = tpdu[6:6+((sender_length+1)//2)*2]
    sender: str = decode_number(sender_number, sender_length)
    if sender_type.lower() == '91':
        sender = '+' + sender

    pid_index: int = 6 + ((sender_length +1)//2)*2
    pid: str = tpdu[pid_index: pid_index+2]
    dcs: int = int(tpdu[pid_index+2: pid_index+4], 16)
    scts_index: int = pid_index + 4
    scts: str = tpdu[scts_index: scts_index + 14]

    ud_index: int = scts_index + 14
    udl: int = int(tpdu[ud_index: ud_index+2], 16)
    user_data_hex: str = tpdu[ud_index+2:]
    user_data_bytes: bytearray = bytearray.fromhex(user_data_hex)

    # 根据 DCS 判断编码
    if dcs == 8:
        await logger.debug("UCS2 编码")
        text: str = user_data_bytes[:udl*2].decode('utf-16-be')
    elif dcs & 0x0C == 0x00:
        await logger.debug("GSM 7-bit 编码")
        text: str = decode_7bit(user_data_hex, udl)
    elif dcs & 0x0C == 0x04:
        await logger.debug("8-bit 编码")
        text: str = user_data_bytes[:udl].decode('latin-1')
    else:
        await logger.debug("未知编码")
        text: str = user_data_bytes.hex()

    return sca_number, sender, text

def apply(ctx: Context):
    logger = ctx.logger("pdu")
    sub = ctx.register('pdu')
    
    async def _decode_pdu(pdu: str) -> tuple[str, str, str]:
        """解码 PDU 格式短信，返回 SCA、发送者和短信文本"""
        return await decode_pdu(logger,pdu)
    
    sub.register('decode',_decode_pdu)
    return sub

inject = ["logger"]
