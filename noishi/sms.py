from noishi import Context as RawContext, Service
from noishi.event import serial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Sms as ExtendContext
    class Context(RawContext,ExtendContext): ...
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

class AtSmsService(Service[Context]):
    def __init__(self, ctx: Context):
        super().__init__(ctx)
        self.buffer = ""
        self.logger = ctx.logger("sms")
        self._running = True
        
        self.pending_lines: list[str] = []
        self.pending_command = False
        self.last_delete_index = None
        
        ctx.register_event_handler(self.handle_serial_rx)
    
    async def handle_serial_rx(self, event: serial.SerialDataReceived):
        if not self._running:
            return
            
        data_str = event.data.decode(errors="ignore")
        self.buffer += data_str

        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            line = line.strip()
            if not line:
                continue

            await self.logger.debug(f"串口输入: {line}")

            if line.startswith('+CMTI:'):
                cmti_data = at_expect(line, "+CMTI: ")
                if cmti_data:
                    parts = cmti_data[0].split(',')
                    if len(parts) == 2:
                        index = parts[1].strip()
                        self.last_delete_index = index
                        await self.logger.info(f"检测到新短信索引: {index}")
                        await self.ctx.send_event(
                            serial.SerialWriteRequest(event.port, f"AT+CMGR={index}\r".encode())
                        )
                        self.pending_command = True
                        self.pending_lines.clear()
                continue

            if self.pending_command:
                self.pending_lines.append(line)

                if line in ("OK", "ERROR"):
                    result_text = "\n".join(self.pending_lines)
                    await self.logger.debug(f"AT命令完整响应:\n{result_text}")
                    self.pending_command = False

                    try:
                        lines = result_text.splitlines()
                        for i, line in enumerate(lines):
                            if line.startswith("+CMGR:"):
                                if i + 1 < len(lines):
                                    pdu_line = lines[i + 1].strip()
                                    if pdu_line:
                                        try:
                                            sca_number, sender, text = await self.ctx.pdu.decode(pdu_line)
                                            await self.logger.info(
                                                f"\n短信中心: {sca_number}\n发送者: {sender}\n正文: {text}"
                                            )
                                            if self.last_delete_index is not None:
                                                await self.ctx.send_event(
                                                    serial.SerialWriteRequest(
                                                        event.port, f"AT+CMGD={self.last_delete_index}\r".encode()
                                                    )
                                                )
                                                await self.logger.info(f"已删除短信索引: {self.last_delete_index}")
                                                self.last_delete_index = None
                                        except Exception as e:
                                            await self.logger.error(f"PDU解码失败: {e}")
                                        break
                    except Exception as e:
                        await self.logger.error(f"AT 响应解析失败: {e}")

                    self.pending_lines.clear()
                continue

            if line.startswith('+CMGR:'):
                if '\n' in self.buffer:
                    pdu_line, self.buffer = self.buffer.split('\n', 1)
                    pdu_line = pdu_line.strip()
                    if pdu_line:
                        try:
                            sca_number, sender, text = await self.ctx.pdu.decode(pdu_line)
                            await self.logger.info(
                                f"\n短信中心: {sca_number}\n发送者: {sender}\n正文: {text}"
                            )
                            if self.last_delete_index is not None:
                                await self.ctx.send_event(
                                    serial.SerialWriteRequest(
                                        event.port, f"AT+CMGD={self.last_delete_index}\r".encode()
                                    )
                                )
                                await self.logger.info(f"已删除短信索引: {self.last_delete_index}")
                                self.last_delete_index = None
                        except Exception as e:
                            await self.logger.error(f"PDU解码失败: {e}")
                continue
    
    def unregister(self):
        self._running = False
        self.ctx.unregister_event_handler(self.handle_serial_rx)
        
def apply(ctx: Context):
    ctx.register("sms", AtSmsService(ctx))

inject = ["logger", "pdu", "serial"]