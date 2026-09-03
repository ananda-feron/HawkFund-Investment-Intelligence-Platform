class AIError(ValueError):
    pass


class ToolAuthorizationDenied(AIError):
    pass


class InvalidToolCall(AIError):
    pass


class DataUnavailable(AIError):
    pass


class ModelProtocolError(AIError):
    pass
