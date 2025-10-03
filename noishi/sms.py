from noishi import Context as RawContext
from noishi.event import serial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Sms as ExtendContext
    class Context(ExtendContext, RawContext): ...
else:
    Context = RawContext
    
def at_expect(text: str, expected: str) -> list[str]:
    result = []
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == "OK":
            break
        if line == "ERROR":
            raise RuntimeError("AT command error")
        if expected and line.startswith(expected):
            result.append(line[len(expected):].lstrip())
    return result

def apply(ctx: Context):
    buffer = ""
    logger = ctx.logger("sms")
    
    @ctx.register_event_handler
    async def handle_serial_rx(event: serial.SerialDataReceived):
        nonlocal buffer
        data_str = event.data.decode()
        buffer += data_str

        while '\n' in buffer:
            line, buffer = buffer.split('\n', 1)
            line = line.strip()
            if not line:
                continue

            await logger.info(f"串口接收: {line}")

            if line.startswith('+CMTI:'):
                cmti_data = at_expect(line, "+CMTI: ")
                if cmti_data:
                    # "ME",0
                    parts = cmti_data[0].split(',')
                    if len(parts) == 2:
                        index = parts[1].strip()
                        await logger.info(f"检测到新短信索引: {index}")
                        await ctx.send_event(serial.SerialWriteRequest(
                            event.port, f"AT+CMGR={index}\r".encode()
                        ))
                continue

            if line.startswith('+CMGR:'):
                # +CMGR: 1,,30
                if '\n' in buffer:
                    pdu_line, buffer = buffer.split('\n', 1)
                    pdu_line = pdu_line.strip()
                    if pdu_line:
                        try:
                            sca_number, sender, text = await ctx.pdu.decode(pdu_line)
                            await logger.info(
                                f"\n短信中心: {sca_number}\n发送者: {sender}\n正文: {text}"
                            )
                            # 解析完成后删除短信
                            index = line.split(':')[1].split(',')[0].strip()
                            await ctx.send_event(serial.SerialWriteRequest(
                                event.port, f"AT+CMGD={index}\r".encode()
                            ))
                            await logger.info(f"已删除短信索引: {index}")
                        except Exception as e:
                            await logger.error(f"PDU解码失败: {e}")

inject = ["logger","pdu","serial"]