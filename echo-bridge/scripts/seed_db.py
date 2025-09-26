"""Seed the echo-bridge SQLite DB with a small test chunk.

Run this with the project venv python so it uses the same environment as the server.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_bridge.main import settings
from echo_bridge.db import init_db
from echo_bridge.services.memory_service import add_chunks


def main() -> None:
    db_path = settings.db_path
    print(f"Initializing DB at: {db_path}")
    init_db(db_path)
    print("Adding sample chunk...")
    added = add_chunks("seed", "sample", ["Hello from ECHO-BRIDGE. This is a seeded test chunk."], {"seeded": True})
    print(f"Added {added} chunk(s)")


if __name__ == '__main__':
    main()
