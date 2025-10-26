from noishi import Context as RawContext, Service
from noishi.event import serial
from noishi.event import sms
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noishi.etype.ctx import ExtendContext_Noishi_Sms as ExtendContext
    class Context(RawContext,ExtendContext): ...
else:
    Context = RawContext

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

        data_str = event.data.decode()
        self.buffer += data_str

        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            line = line.strip()
            if not line:
                continue

            await self.logger.debug(f"串口输入: {line}")

            if line.startswith('+CMTI:'):
                cmti_data = self.ctx.at.command.export(line, "+CMTI: ")
                if cmti_data:
                    parts = cmti_data[0].split(',')
                    if len(parts) == 2:
                        index = parts[1].strip()
                        self.last_delete_index = index
                        await self.logger.debug(f"检测到新短信索引: {index}")
                        await self.ctx.send_event(
                            serial.SerialWriteRequest(event.port, self.ctx.at.command.build("+CMGR", index).encode())
                        )
                        self.pending_command = True
                        self.pending_lines.clear()
                continue

            if line.startswith('+CMT:'):
                pdu_line, self.buffer = self.buffer.split('\n', 1)
                pdu_line = pdu_line.strip()
                if pdu_line:
                    sca_number, sender, text, text_type = self.ctx.pdu.decode(pdu_line)
                    await self.ctx.send_event(sms.SmsReceived(sca_number, sender, text, text_type))
                continue

            if self.pending_command:
                self.pending_lines.append(line)

                if line in ("OK", "ERROR"):
                    result_text = "\n".join(self.pending_lines)
                    await self.logger.debug(f"AT命令完整响应:\n{result_text}")
                    self.pending_command = False
                    lines = result_text.splitlines()
                    for i, line in enumerate(lines):
                        if line.startswith("+CMGR:"):
                            if i + 1 < len(lines):
                                pdu_line = lines[i + 1].strip()
                                if pdu_line:
                                    sca_number, sender, text, text_type = self.ctx.pdu.decode(pdu_line)
                                    await self.ctx.send_event(sms.SmsReceived(sca_number, sender, text, text_type))
                                    if self.last_delete_index is not None:
                                        await self.ctx.send_event(
                                            serial.SerialWriteRequest(
                                                event.port, self.ctx.at.command.build("+CMGD", self.last_delete_index, 0).encode()
                                            )
                                        )
                                        await self.logger.debug(f"已删除短信索引: {self.last_delete_index}")
                                        self.last_delete_index = None
                                    break
                    self.pending_lines.clear()
                continue
    
    def unregister(self):
        self._running = False
        self.ctx.unregister_event_handler(self.handle_serial_rx)
        
def apply(ctx: Context):
    ctx.register("sms", AtSmsService(ctx))

inject = ["logger", "pdu", "at", "serial"]