from noishi import Event

class SerialDataReceived(Event):
    def __init__(self, port: str, data: bytes):
        self.port = port
        self.data = data

    def __str__(self):
        return f"RX({self.port}): {self.data!r}"

class SerialWriteRequest(Event):
    def __init__(self, port: str, data: bytes):
        self.port = port
        self.data = data

    def __str__(self):
        return f"TX-REQ({self.port}): {self.data!r}"

class SerialDataSent(Event):
    def __init__(self, port: str, data: bytes):
        self.port = port
        self.data = data

    def __str__(self):
        return f"TX({self.port}): {self.data!r}"