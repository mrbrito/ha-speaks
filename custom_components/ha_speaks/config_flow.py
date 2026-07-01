from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ALEXA_TARGETS,
    CONF_GROUPS,
    CONF_MEDIA_PLAYER_ENTITY_IDS,
    CONF_TTS_ENTITY_ID,
    DOMAIN,
)


class HaSpeaksConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="HA Speaks",
                data={CONF_TTS_ENTITY_ID: user_input[CONF_TTS_ENTITY_ID]},
                options={CONF_GROUPS: []},
            )

        tts_entities = self.hass.states.async_entity_ids("tts")
        if not tts_entities:
            errors["base"] = "no_tts_entities"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TTS_ENTITY_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=tts_entities,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return HaSpeaksOptionsFlow()


class HaSpeaksOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        self._ensure_options()

        if user_input is not None:
            action = user_input["action"]
            if action == "finish":
                return self.async_create_entry(title="", data=self.options)
            return await getattr(self, f"async_step_{action}")()

        actions = [
            {"value": "settings", "label": "Change TTS entity"},
            {"value": "add_group", "label": "Add speech group"},
        ]
        if self.options.get(CONF_GROUPS):
            actions.append({"value": "remove_group", "label": "Remove speech group"})
        actions.append({"value": "finish", "label": "Finish"})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): vol.In(
                        {action["value"]: action["label"] for action in actions}
                    )
                }
            ),
        )

    async def async_step_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        if user_input is not None:
            self.options[CONF_TTS_ENTITY_ID] = user_input[CONF_TTS_ENTITY_ID]
            return await self.async_step_init()

        tts_entities = self.hass.states.async_entity_ids("tts")
        current = self.options.get(CONF_TTS_ENTITY_ID) or self.config_entry.data.get(
            CONF_TTS_ENTITY_ID
        )

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TTS_ENTITY_ID, default=current or ""): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=tts_entities or ([current] if current else []),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_add_group(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        if user_input is not None:
            groups = list(self.options.get(CONF_GROUPS, []))
            groups = [
                group
                for group in groups
                if _group_name(group).casefold() != user_input[CONF_NAME].casefold()
            ]
            groups.append(
                {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_MEDIA_PLAYER_ENTITY_IDS: user_input.get(
                        CONF_MEDIA_PLAYER_ENTITY_IDS, []
                    ),
                    CONF_ALEXA_TARGETS: _csv_to_list(user_input.get(CONF_ALEXA_TARGETS, "")),
                }
            )
            self.options[CONF_GROUPS] = groups
            return await self.async_step_init()

        return self.async_show_form(
            step_id="add_group",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Optional(CONF_MEDIA_PLAYER_ENTITY_IDS, default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="media_player", multiple=True)
                    ),
                    vol.Optional(CONF_ALEXA_TARGETS, default=""): str,
                }
            ),
        )

    async def async_step_remove_group(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        groups = list(self.options.get(CONF_GROUPS, []))
        if user_input is not None:
            self.options[CONF_GROUPS] = [
                group for group in groups if _group_name(group) != user_input[CONF_NAME]
            ]
            return await self.async_step_init()

        group_names = [_group_name(group) for group in groups]

        return self.async_show_form(
            step_id="remove_group",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): vol.In(group_names)
                }
            ),
        )

    def _ensure_options(self) -> None:
        if hasattr(self, "options"):
            return

        self.options = dict(self.config_entry.options)
        self.options.setdefault(CONF_GROUPS, [])


def _csv_to_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _group_name(group: dict[str, Any]) -> str:
    return group.get(CONF_NAME, group.get("name", ""))
