"""`python -m app.mcp` — the command a model's client spawns."""

from app.mcp.server import build

if __name__ == "__main__":
    build().run("stdio")
