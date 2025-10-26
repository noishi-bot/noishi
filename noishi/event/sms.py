from noishi import Event

class SmsReceived(Event):
    def __init__(self, sca_number: str, sender: str, text: str, text_type: str):
        self.sca_number = sca_number
        self.sender = sender
        self.text = text
        self.text_type = text_type
            
    def __str__(self):
        return f"SmsReceived(from={self.sender}, text_type={self.text_type}, text={self.text}, sca_number={self.sca_number})"