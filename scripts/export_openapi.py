# pyright: reportMissingTypeStubs=false
"""Export OpenAPI spec from FastAPI app."""

import json
from pathlib import Path

from agent_review.app import create_app
from agent_review.config import Settings

settings = Settings(database_url="sqlite+aiosqlite://")
app = create_app(settings)
schema = app.openapi()

output = Path("frontend/openapi.json")
_ = output.write_text(json.dumps(schema, indent=2))
print(f"Wrote {output}")
