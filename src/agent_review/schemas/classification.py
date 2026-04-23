from pydantic import BaseModel, Field


class Classification(BaseModel):
    change_type: str
    domains: list[str]
    risk_level: str
    profiles: list[str]
    file_categories: dict[str, list[str]]
    detected_languages: list[str] = Field(default_factory=list)
