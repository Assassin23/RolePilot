from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field

from src.schemas.job import CanonicalJob


class ProviderFetchResult(BaseModel):
    provider_name: str
    board_or_query: str
    jobs: List[CanonicalJob] = Field(default_factory=list)
    total_found: int = 0
    status: str = "SUCCESS"  # "SUCCESS", "PARTIAL", "FAILED"
    error_message: Optional[str] = None


class BaseJobProvider(ABC):
    """Abstract Base Class for job discovery source providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'greenhouse', 'jobgether')."""
        pass

    @abstractmethod
    async def fetch_jobs(self, identifier_or_query: str, **kwargs) -> ProviderFetchResult:
        """
        Fetches and normalizes jobs from the provider.
        Must handle errors gracefully and return a ProviderFetchResult.
        """
        pass
