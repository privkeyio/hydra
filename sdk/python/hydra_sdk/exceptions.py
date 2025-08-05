class HydraError(Exception):
    pass


class HydraAPIError(HydraError):
    def __init__(self, status_code: int, message: str, response: dict = None):
        self.status_code = status_code
        self.message = message
        self.response = response or {}
        super().__init__(f"API Error {status_code}: {message}")


class HydraTimeoutError(HydraError):
    pass


class HydraRateLimitError(HydraAPIError):
    pass


class HydraAuthenticationError(HydraAPIError):
    pass
