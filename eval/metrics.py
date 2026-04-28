try:
    from deepeval.metrics import BaseMetric
except ModuleNotFoundError:
    class BaseMetric:
        """Small local fallback so unit tests do not require DeepEval installed."""

        def __init__(self):
            self.threshold = 0.0
            self.score = 0.0

from eval.schemas import EvalResult


class RecallMetric(BaseMetric):
    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.score = 0.0

    @property
    def __name__(self):
        return "RecallMetric"

    def measure(self, result: EvalResult, *args, **kwargs) -> float:
        self.score = result.score.recall
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, result: EvalResult, *args, **kwargs) -> float:
        return self.measure(result)


class PrecisionMetric(BaseMetric):
    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.score = 0.0

    @property
    def __name__(self):
        return "PrecisionMetric"

    def measure(self, result: EvalResult, *args, **kwargs) -> float:
        self.score = result.score.precision
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, result: EvalResult, *args, **kwargs) -> float:
        return self.measure(result)


class ValidityMetric(BaseMetric):
    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0

    @property
    def __name__(self):
        return "ValidityMetric"

    def measure(self, result: EvalResult, *args, **kwargs) -> float:
        try:
            result.review.model_dump()
            self.score = 1.0
        except Exception:
            self.score = 0.0
        return self.score

    def is_successful(self) -> bool:
        return self.score >= self.threshold

    async def a_measure(self, result: EvalResult, *args, **kwargs) -> float:
        return self.measure(result)


class LatencyMetric(BaseMetric):
    def __init__(self, threshold_ms: int = 5000):
        self.threshold_ms = threshold_ms
        self.threshold = threshold_ms
        self.score = 0.0

    @property
    def __name__(self):
        return "LatencyMetric"

    def measure(self, result: EvalResult, *args, **kwargs) -> float:
        self.score = result.review.latency_ms / self.threshold_ms
        return self.score

    def is_successful(self) -> bool:
        return self.score <= 1.0

    async def a_measure(self, result: EvalResult, *args, **kwargs) -> float:
        return self.measure(result)


class CostMetric(BaseMetric):
    def __init__(self, threshold_usd: float = 0.05):
        self.threshold_usd = threshold_usd
        self.threshold = threshold_usd
        self.score = None
        self.measured = False

    @property
    def __name__(self):
        return "CostMetric"

    def measure(self, result: EvalResult, *args, **kwargs) -> float | None:
        if result.review.cost_usd is None:
            self.score = None
            self.measured = False
            return self.score
        self.score = result.review.cost_usd / self.threshold_usd
        self.measured = True
        return self.score

    def is_successful(self) -> bool:
        if not self.measured:
            return False
        return self.score <= 1.0

    async def a_measure(self, result: EvalResult, *args, **kwargs) -> float | None:
        return self.measure(result)
