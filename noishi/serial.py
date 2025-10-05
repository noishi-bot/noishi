import asyncio
import serial_asyncio
import weakref
from noishi import Context, Service
from noishi.event.serial import SerialDataSent, SerialDataReceived, SerialWriteRequest

class SerialService(Service[Context]):
    def __init__(self, ctx: Context, port: str, baudrate: int = 115200):
        super().__init__(ctx)
        self.port = port
        self.baudrate = baudrate
        self._running = True
        self.transport = None
        self.protocol = None
        ctx.register_event_handler(self.handle_write)
        asyncio.create_task(self.start_serial())
        
    async def handle_write(self,event: SerialWriteRequest):
        if event.port == self.port and self.transport:
            self.transport.write(event.data)
            await self.ctx.send_event(SerialDataSent(self.port, event.data))
            
    async def start_serial(self):
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await serial_asyncio.create_serial_connection(
            loop, lambda: SerialProtocol(self), self.port, baudrate=self.baudrate
        )

    def unregister(self):
        self._running = False
        if self.transport:
            self.transport.close()
        self.ctx.unregister_event_handler(self.handle_write)

class SerialProtocol(asyncio.Protocol):
    def __init__(self, service: SerialService):
        self.service_ref = weakref.ref(service)
        self.buffer = bytearray()

    def data_received(self, data: bytes):
        self.buffer.extend(data)
        service = self.service_ref()
        if service is not None and service._running:
            asyncio.create_task(service.ctx.send_event(
                SerialDataReceived(service.port, bytes(data))
            ))

def apply(ctx: Context, port: str, baudrate: int = 115200):
    ctx.register("serial", SerialService(ctx, port, baudrate))
