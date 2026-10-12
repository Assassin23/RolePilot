from pathlib import Path
from typing import List
import yaml
from pydantic import BaseModel, Field


class BoardConfig(BaseModel):
    token: str
    company_name: str
    enabled: bool = True
    notes: str = ""


class AppConfig(BaseModel):
    boards: List[BoardConfig] = Field(default_factory=list)

    @classmethod
    def load_from_yaml(cls, path: str | Path = "config/boards.yaml") -> "AppConfig":
        file_path = Path(path)
        if not file_path.exists():
            return cls(boards=[])
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    def get_enabled_boards(self) -> List[BoardConfig]:
        return [b for b in self.boards if b.enabled]
