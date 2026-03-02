"""Seed an initial admin user for NEXUS.

Usage:
    python scripts/seed_admin.py
    docker compose exec api python scripts/seed_admin.py

Environment variables (or .env):
    ADMIN_EMAIL    — admin email (default: admin@nexus.local)
    ADMIN_PASSWORD — admin password (default: auto-generated)
    ADMIN_NAME     — admin full name (default: NEXUS Admin)
"""

from __future__ import annotations

import os
import secrets
import sys

from sqlalchemy import create_engine, text

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth.service import AuthService
from app.config import Settings


def main() -> None:
    settings = Settings()
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)

    email = os.environ.get("ADMIN_EMAIL", "admin@nexus-demo.com")
    password = os.environ.get("ADMIN_PASSWORD", "")
    full_name = os.environ.get("ADMIN_NAME", "NEXUS Admin")

    generated = False
    if not password:
        password = secrets.token_urlsafe(16)
        generated = True

    with engine.connect() as conn:
        # Check if user already exists
        result = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        )
        if result.first() is not None:
            print(f"User '{email}' already exists — skipping.")
            return

        # Create admin user
        password_hash = AuthService.hash_password(password)
        from datetime import UTC, datetime
        from uuid import uuid4

        user_id = uuid4()
        now = datetime.now(UTC)

        conn.execute(
            text("""
                INSERT INTO users (id, email, password_hash, full_name, role, created_at, updated_at)
                VALUES (:id, :email, :password_hash, :full_name, :role, :created_at, :updated_at)
            """),
            {
                "id": user_id,
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name,
                "role": "admin",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()

    print(f"Admin user created: {email}")
    if generated:
        print(f"Generated password: {password}")
        print("(Set ADMIN_PASSWORD env var to use a specific password)")


if __name__ == "__main__":
    main()
