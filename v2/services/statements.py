"""Domain errors for participant statement commands."""


class StatementQuotaExceeded(RuntimeError):
    pass


class UnknownParentStatement(ValueError):
    pass


class StatementPreparationUnavailable(RuntimeError):
    """The upstream session failed before a statement POST was attempted."""


class DerivativeSimilarityTooLow(RuntimeError):
    def __init__(self, *, model: str | None, similarity: float | None,
                 threshold: float):
        super().__init__('The wording is too far from its parent statement.')
        self.model = model
        self.similarity = similarity
        self.threshold = threshold
