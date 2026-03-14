"""Settings registry service — CRUD, Settings mutation, and DI cache clearing."""

from __future__ import annotations

import json
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings_registry.registry import SETTING_REGISTRY, SettingMeta
from app.settings_registry.schemas import (
    SettingDetail,
    SettingType,
    SettingUpdateResponse,
)

logger = structlog.get_logger(__name__)


class SettingsRegistryService:
    """Static methods for runtime tuning settings management."""

    @staticmethod
    async def list_settings(db: AsyncSession) -> list[SettingDetail]:
        """List all tunable settings with current values and override status."""
        from app.dependencies import get_settings

        settings = get_settings()

        # Fetch DB overrides
        result = await db.execute(
            text("""
                SELECT setting_name, value, updated_at, updated_by
                FROM setting_overrides
            """)
        )
        overrides = {r["setting_name"]: dict(r) for r in result.mappings().all()}

        items: list[SettingDetail] = []
        for setting_name, meta in SETTING_REGISTRY.items():
            override = overrides.get(setting_name)
            env_default = _settings_env_default(setting_name, meta)
            current_value = getattr(settings, setting_name)

            # Check if parent feature flag is enabled
            flag_enabled = None
            if meta.requires_flag:
                flag_enabled = getattr(settings, meta.requires_flag, False)

            items.append(
                SettingDetail(
                    setting_name=setting_name,
                    display_name=meta.display_name,
                    description=meta.description,
                    category=meta.category,
                    setting_type=meta.setting_type,
                    risk_level=meta.risk_level,
                    value=current_value,
                    env_default=env_default,
                    min_value=meta.min_value,
                    max_value=meta.max_value,
                    unit=meta.unit,
                    step=meta.step,
                    is_override=override is not None,
                    updated_at=override["updated_at"] if override else None,
                    updated_by=override["updated_by"] if override else None,
                    requires_flag=meta.requires_flag,
                    flag_enabled=flag_enabled,
                )
            )

        return items

    @staticmethod
    async def update_setting(
        db: AsyncSession,
        setting_name: str,
        value: int | float | str,
        user_id: UUID | None = None,
    ) -> SettingUpdateResponse:
        """Update a setting: validate, UPSERT DB override, mutate Settings, clear DI caches."""
        if setting_name not in SETTING_REGISTRY:
            raise ValueError(f"Unknown setting: {setting_name}")

        meta = SETTING_REGISTRY[setting_name]

        # Type coerce and validate
        coerced = _coerce_value(value, meta)
        _validate_range(coerced, meta, setting_name)

        # JSON-encode for storage
        json_value = json.dumps(coerced)

        # UPSERT override
        result = await db.execute(
            text("""
                INSERT INTO setting_overrides (setting_name, value, updated_by, updated_at)
                VALUES (:setting_name, :value, :updated_by, now())
                ON CONFLICT (setting_name) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                RETURNING setting_name, value, updated_at, updated_by
            """),
            {
                "setting_name": setting_name,
                "value": json_value,
                "updated_by": user_id,
            },
        )
        row = result.mappings().one()

        # Mutate Settings singleton
        from app.dependencies import get_settings

        settings = get_settings()
        setattr(settings, setting_name, coerced)
        logger.info("setting.updated", setting=setting_name, value=coerced)

        # Clear DI caches
        caches_cleared = _clear_di_caches(meta.di_caches)

        # Check flag status
        flag_enabled = None
        if meta.requires_flag:
            flag_enabled = getattr(settings, meta.requires_flag, False)

        return SettingUpdateResponse(
            setting_name=setting_name,
            display_name=meta.display_name,
            description=meta.description,
            category=meta.category,
            setting_type=meta.setting_type,
            risk_level=meta.risk_level,
            value=coerced,
            env_default=_settings_env_default(setting_name, meta),
            min_value=meta.min_value,
            max_value=meta.max_value,
            unit=meta.unit,
            step=meta.step,
            is_override=True,
            updated_at=row["updated_at"],
            updated_by=row["updated_by"],
            requires_flag=meta.requires_flag,
            flag_enabled=flag_enabled,
            caches_cleared=caches_cleared,
            restart_required=meta.risk_level == "restart",
        )

    @staticmethod
    async def reset_setting(db: AsyncSession, setting_name: str) -> None:
        """Remove DB override, revert Settings to env default, clear DI caches."""
        if setting_name not in SETTING_REGISTRY:
            raise ValueError(f"Unknown setting: {setting_name}")

        meta = SETTING_REGISTRY[setting_name]

        await db.execute(
            text("DELETE FROM setting_overrides WHERE setting_name = :setting_name"),
            {"setting_name": setting_name},
        )

        # Revert to env default
        from app.dependencies import get_settings

        settings = get_settings()
        env_default = _settings_env_default(setting_name, meta)
        setattr(settings, setting_name, env_default)
        logger.info("setting.reset", setting=setting_name, env_default=env_default)

        _clear_di_caches(meta.di_caches)

    @staticmethod
    async def load_overrides_into_settings(db: AsyncSession) -> None:
        """Load all DB overrides into the Settings singleton. Called at startup."""
        from app.dependencies import get_settings

        settings = get_settings()

        result = await db.execute(text("SELECT setting_name, value FROM setting_overrides"))
        rows = result.mappings().all()
        if not rows:
            return

        for row in rows:
            setting_name = row["setting_name"]
            if setting_name in SETTING_REGISTRY and hasattr(settings, setting_name):
                meta = SETTING_REGISTRY[setting_name]
                try:
                    parsed = json.loads(row["value"])
                    coerced = _coerce_value(parsed, meta)
                    setattr(settings, setting_name, coerced)
                    logger.info("setting.override_loaded", setting=setting_name, value=coerced)
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning("setting.override_invalid", setting=setting_name, raw=row["value"])

        logger.info("settings.overrides_loaded", count=len(rows))


def load_setting_overrides_sync(settings: object, engine: object) -> None:
    """Load DB setting overrides into a Settings instance (sync).

    Called by Celery tasks so each execution picks up the latest
    admin-configured values without a worker restart.
    """
    with engine.connect() as conn:
        result = conn.execute(text("SELECT setting_name, value FROM setting_overrides"))
        rows = result.mappings().all()
    if not rows:
        return
    for row in rows:
        setting_name = row["setting_name"]
        if setting_name in SETTING_REGISTRY and hasattr(settings, setting_name):
            meta = SETTING_REGISTRY[setting_name]
            try:
                parsed = json.loads(row["value"])
                coerced = _coerce_value(parsed, meta)
                setattr(settings, setting_name, coerced)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass


def load_setting_overrides_sync_safe(settings: object, engine: object) -> None:
    """Like load_setting_overrides_sync but logs and continues on failure.

    Safe for Celery tasks where the setting_overrides table may not exist yet.
    """
    try:
        load_setting_overrides_sync(settings, engine)
    except Exception:
        logger.warning("settings.sync_load_failed", exc_info=True)


def _settings_env_default(setting_name: str, meta: SettingMeta) -> int | float | str:
    """Get the env-file default for a setting by reading Settings model field defaults."""
    from app.config import Settings

    field_info = Settings.model_fields.get(setting_name)
    if field_info is None:
        return 0
    default = field_info.default
    if default is None:
        return 0
    return _coerce_value(default, meta)


def _coerce_value(value: int | float | str, meta: SettingMeta) -> int | float | str:
    """Coerce a value to the expected type based on the setting's metadata."""
    if meta.setting_type == SettingType.INT:
        return int(value)
    elif meta.setting_type == SettingType.FLOAT:
        return float(value)
    return str(value)


def _validate_range(
    value: int | float | str,
    meta: SettingMeta,
    setting_name: str,
) -> None:
    """Validate a numeric value is within the registry-defined range."""
    if isinstance(value, str):
        return  # no range validation for string settings
    if meta.min_value is not None and value < meta.min_value:
        raise ValueError(f"{setting_name}: value {value} below minimum {meta.min_value}")
    if meta.max_value is not None and value > meta.max_value:
        raise ValueError(f"{setting_name}: value {value} above maximum {meta.max_value}")


def _clear_di_caches(cache_names: list[str]) -> list[str]:
    """Clear specified DI factory caches. Returns names of caches actually cleared."""
    from app import dependencies

    cleared: list[str] = []
    for cache_name in cache_names:
        factory = getattr(dependencies, cache_name, None)
        if factory is not None and hasattr(factory, "cache_clear"):
            factory.cache_clear()
            cleared.append(cache_name)
            logger.info("setting.cache_cleared", cache=cache_name)
    return cleared
