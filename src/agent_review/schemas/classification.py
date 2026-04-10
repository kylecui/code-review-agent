from pydantic import BaseModel


class Classification(BaseModel):
    change_type: str
    domains: list[str]
    risk_level: str
    profiles: list[str]
    file_categories: dict[str, list[str]]
