"""Fix admin user credentials for local development.

Updates the admin user to use admin@example.com / password123.
If no admin user exists, creates one with these credentials and links
to the default matter.

Usage:
    python scripts/fix_admin_password.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, text

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth.service import AuthService
from app.config import Settings

_TARGET_EMAIL = "admin@example.com"
_TARGET_PASSWORD = "password123"
_TARGET_NAME = "System Administrator"
_DEFAULT_MATTER_ID = "00000000-0000-0000-0000-000000000001"


def main() -> None:
    settings = Settings()
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    password_hash = AuthService.hash_password(_TARGET_PASSWORD)
    now = datetime.now(UTC)

    with engine.connect() as conn:
        # Check if target email already exists
        existing = conn.execute(
            text("SELECT id, role FROM users WHERE email = :email"),
            {"email": _TARGET_EMAIL},
        )
        existing_row = existing.first()

        if existing_row is not None:
            # Target email already exists — just update password and ensure admin role
            conn.execute(
                text("""
                    UPDATE users
                    SET password_hash = :password_hash, role = 'admin',
                        full_name = :full_name, updated_at = :updated_at
                    WHERE email = :email
                """),
                {
                    "email": _TARGET_EMAIL,
                    "password_hash": password_hash,
                    "full_name": _TARGET_NAME,
                    "updated_at": now,
                },
            )
            conn.commit()
            print(f"Updated existing user {_TARGET_EMAIL} with new password hash")
            print(f"Credentials: {_TARGET_EMAIL} / {_TARGET_PASSWORD}")
            return

        # Check for admin user with different email (migration-seeded)
        result = conn.execute(text("SELECT id, email FROM users WHERE role = 'admin' LIMIT 1"))
        row = result.first()

        if row is not None:
            # Update existing admin user's email and password
            conn.execute(
                text("""
                    UPDATE users
                    SET email = :email, password_hash = :password_hash,
                        full_name = :full_name, updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": row.id,
                    "email": _TARGET_EMAIL,
                    "password_hash": password_hash,
                    "full_name": _TARGET_NAME,
                    "updated_at": now,
                },
            )
            conn.commit()
            print(f"Updated admin user (was {row.email}) -> {_TARGET_EMAIL} / {_TARGET_PASSWORD}")
        else:
            # Create new admin user
            user_id = uuid4()
            conn.execute(
                text("""
                    INSERT INTO users (id, email, password_hash, full_name, role, created_at, updated_at)
                    VALUES (:id, :email, :password_hash, :full_name, :role, :created_at, :updated_at)
                """),
                {
                    "id": user_id,
                    "email": _TARGET_EMAIL,
                    "password_hash": password_hash,
                    "full_name": _TARGET_NAME,
                    "role": "admin",
                    "created_at": now,
                    "updated_at": now,
                },
            )

            # Ensure default matter exists
            matter_result = conn.execute(
                text("SELECT id FROM case_matters WHERE id = :id"),
                {"id": _DEFAULT_MATTER_ID},
            )
            if matter_result.first() is None:
                conn.execute(
                    text("""
                        INSERT INTO case_matters (id, name, description)
                        VALUES (:id, :name, :description)
                    """),
                    {
                        "id": _DEFAULT_MATTER_ID,
                        "name": "Default Matter",
                        "description": "Default case matter for development and testing",
                    },
                )

            # Link admin to default matter
            conn.execute(
                text("""
                    INSERT INTO user_case_matters (user_id, matter_id)
                    VALUES (:user_id, :matter_id)
                    ON CONFLICT DO NOTHING
                """),
                {"user_id": user_id, "matter_id": _DEFAULT_MATTER_ID},
            )
            conn.commit()
            print(f"Created admin user: {_TARGET_EMAIL} / {_TARGET_PASSWORD}")


if __name__ == "__main__":
    main()
