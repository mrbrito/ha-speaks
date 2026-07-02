from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ALEXA_MEDIA_PLAYER_ENTITY_IDS,
    CONF_ALEXA_TARGETS,
    CONF_GROUPS,
    CONF_MEDIA_PLAYER_ENTITY_IDS,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    groups = entry.options.get(CONF_GROUPS, [])
    async_add_entities(
        HaSpeaksGroupSensor(entry, group)
        for group in groups
        if _group_name(group)
    )


class HaSpeaksGroupSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:speaker-message"

    def __init__(self, entry: ConfigEntry, group: dict[str, Any]) -> None:
        self._entry = entry
        self._group = group
        self._group_name = _group_name(group)
        self._attr_name = self._group_name
        self._attr_unique_id = f"{entry.entry_id}_{_slug(self._group_name)}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="HA Speaks",
            manufacturer="HA Speaks",
        )

    @property
    def native_value(self) -> int:
        return (
            len(self._media_players)
            + len(self._alexa_media_players)
            + len(self._alexa_targets)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "group": self._group_name,
            "media_player_entity_ids": self._media_players,
            "alexa_media_player_entity_ids": self._alexa_media_players,
            "alexa_targets": self._alexa_targets,
            "media_player_count": len(self._media_players),
            "alexa_media_player_count": len(self._alexa_media_players),
            "alexa_target_count": len(self._alexa_targets),
        }

    @property
    def _media_players(self) -> list[str]:
        return list(self._group.get(CONF_MEDIA_PLAYER_ENTITY_IDS, []))

    @property
    def _alexa_media_players(self) -> list[str]:
        return list(self._group.get(CONF_ALEXA_MEDIA_PLAYER_ENTITY_IDS, []))

    @property
    def _alexa_targets(self) -> list[str]:
        return list(self._group.get(CONF_ALEXA_TARGETS, []))


def _group_name(group: dict[str, Any]) -> str:
    return group.get(CONF_NAME, group.get("name", ""))


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
