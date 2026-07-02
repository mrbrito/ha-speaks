from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ALEXA_MEDIA_PLAYER_ENTITY_IDS,
    CONF_ALEXA_TARGETS,
    CONF_GROUPS,
    CONF_MEDIA_PLAYER_ENTITY_IDS,
    CONF_TTS_ENTITY_ID,
    DOMAIN,
    SERVICE_ANNOUNCE,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]

GROUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_MEDIA_PLAYER_ENTITY_IDS, default=[]): cv.ensure_list,
        vol.Optional(CONF_ALEXA_MEDIA_PLAYER_ENTITY_IDS, default=[]): cv.ensure_list,
        vol.Optional(CONF_ALEXA_TARGETS, default=[]): cv.ensure_list,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN, default={}): vol.Schema(
            {
                vol.Optional(CONF_TTS_ENTITY_ID): cv.string,
                vol.Optional(CONF_GROUPS, default=[]): vol.All(cv.ensure_list, [GROUP_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("group"): cv.string,
        vol.Optional("volume"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(CONF_MEDIA_PLAYER_ENTITY_IDS): cv.ensure_list,
        vol.Optional(CONF_ALEXA_MEDIA_PLAYER_ENTITY_IDS): cv.ensure_list,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = config.get(DOMAIN, {})
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if not _configured_sources(hass):
        hass.services.async_remove(DOMAIN, SERVICE_ANNOUNCE)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ANNOUNCE):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_ANNOUNCE,
        _build_announce_handler(hass),
        schema=SERVICE_SCHEMA,
    )


def _build_announce_handler(hass: HomeAssistant):
    async def async_handle_announce(call: ServiceCall) -> None:
        sources = _configured_sources(hass)
        if not sources:
            raise HomeAssistantError("HA Speaks is not configured")

        message: str = call.data["message"]
        group_name: str | None = call.data.get("group")
        volume: float | None = call.data.get("volume")
        explicit_entities = call.data.get(CONF_MEDIA_PLAYER_ENTITY_IDS) or []
        explicit_alexa_entities = call.data.get(CONF_ALEXA_MEDIA_PLAYER_ENTITY_IDS) or []

        media_player_entity_ids: list[str] = list(explicit_entities)
        alexa_media_player_entity_ids: list[str] = list(explicit_alexa_entities)
        alexa_targets: list[str] = []
        tts_entity_id = _first_tts_entity(sources)

        if group_name:
            group = _find_group(sources, group_name)
            if group is None:
                raise HomeAssistantError(f"Unknown HA Speaks group: {group_name}")
            media_player_entity_ids.extend(group.get(CONF_MEDIA_PLAYER_ENTITY_IDS, []))
            alexa_media_player_entity_ids.extend(
                group.get(CONF_ALEXA_MEDIA_PLAYER_ENTITY_IDS, [])
            )
            alexa_targets.extend(group.get(CONF_ALEXA_TARGETS, []))

        media_player_entity_ids = _dedupe(media_player_entity_ids)
        alexa_media_player_entity_ids = _dedupe(alexa_media_player_entity_ids)
        alexa_targets = _dedupe(alexa_targets + alexa_media_player_entity_ids)

        all_volume_media_players = _dedupe(
            media_player_entity_ids + alexa_media_player_entity_ids
        )

        if not media_player_entity_ids and not alexa_targets:
            raise HomeAssistantError("No HA Speaks targets were provided")

        if volume is not None and all_volume_media_players:
            await _set_volume(hass, all_volume_media_players, volume)

        if media_player_entity_ids:
            if not tts_entity_id:
                raise HomeAssistantError("No TTS entity is configured for HA Speaks")
            await _speak_to_media_players(
                hass,
                tts_entity_id,
                media_player_entity_ids,
                message,
            )

        if alexa_targets:
            await _notify_alexa(
                hass,
                alexa_targets,
                message,
                require_service=not media_player_entity_ids,
            )

    return async_handle_announce


def _configured_sources(hass: HomeAssistant) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    yaml_config = hass.data.get(DOMAIN, {}).get("yaml") or {}
    if yaml_config:
        sources.append(yaml_config)

    for entry in hass.config_entries.async_entries(DOMAIN):
        merged = dict(entry.data)
        merged.update(entry.options)
        sources.append(merged)

    return sources


def _first_tts_entity(sources: list[dict[str, Any]]) -> str | None:
    for source in sources:
        value = source.get(CONF_TTS_ENTITY_ID)
        if value:
            return value
    return None


def _find_group(sources: list[dict[str, Any]], group_name: str) -> dict[str, Any] | None:
    normalized = group_name.casefold()
    for source in sources:
        for group in source.get(CONF_GROUPS, []):
            if group.get(CONF_NAME, group.get("name", "")).casefold() == normalized:
                return group
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


async def _set_volume(
    hass: HomeAssistant,
    media_player_entity_ids: list[str],
    volume: float,
) -> None:
    await hass.services.async_call(
        "media_player",
        "volume_set",
        {"volume_level": volume / 100},
        target={"entity_id": media_player_entity_ids},
        blocking=False,
    )


async def _speak_to_media_players(
    hass: HomeAssistant,
    tts_entity_id: str,
    media_player_entity_ids: list[str],
    message: str,
) -> None:
    for entity_id in media_player_entity_ids:
        await hass.services.async_call(
            "tts",
            "speak",
            {
                "media_player_entity_id": entity_id,
                "message": message,
                "cache": True,
            },
            target={"entity_id": tts_entity_id},
            blocking=False,
        )


async def _notify_alexa(
    hass: HomeAssistant,
    alexa_targets: list[str],
    message: str,
    require_service: bool = False,
) -> None:
    if not hass.services.has_service("notify", "alexa_media"):
        if require_service:
            raise HomeAssistantError(
                "notify.alexa_media is not available. Install and configure Alexa Media Player."
            )
        _LOGGER.warning("notify.alexa_media is not available; skipping Alexa targets")
        return

    await hass.services.async_call(
        "notify",
        "alexa_media",
        {
            "message": message,
            "target": alexa_targets,
            "data": {"type": "announce"},
        },
        blocking=False,
    )
