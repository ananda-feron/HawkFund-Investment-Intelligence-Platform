class ImportPipelineError(ValueError):
    """The import batch or source format is invalid."""


class RowNormalizationError(ImportPipelineError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)
