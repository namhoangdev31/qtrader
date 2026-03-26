class QTraderAPI:
    def __init__(self, host="localhost", port=8000) -> None:
        self.host = host
        self.port = port
        self.engine = None

    def get_status(self):
        if self.engine is None:
            return {"running": False}
        return {"running": self.engine.is_running()}
