metadata {
    definition(name: "HA Speaks Speech Engine", namespace: "ha-speaks", author: "Luis + Codex") {
        capability "SpeechSynthesis"
        capability "AudioVolume"
        capability "Actuator"

        command "speakToGroup", [
            [name: "Message", type: "STRING", description: "Text to announce"],
            [name: "Group", type: "STRING", description: "HA Speaks group name"],
            [name: "Volume", type: "NUMBER", description: "0-100 volume"]
        ]
        command "sendAnnouncement", [
            [name: "Message", type: "STRING", description: "Text to announce"],
            [name: "Group", type: "STRING", description: "HA Speaks group name"],
            [name: "Volume", type: "NUMBER", description: "0-100 volume"]
        ]

        attribute "lastMessage", "string"
        attribute "lastGroup", "string"
        attribute "lastStatus", "string"
        attribute "speech", "string"
    }

    preferences {
        input name: "haBaseUrl", type: "text", title: "Home Assistant base URL", required: true, description: "Example: http://homeassistant.local:8123"
        input name: "haToken", type: "password", title: "Home Assistant long-lived access token", required: true
        input name: "defaultGroup", type: "text", title: "Default HA Speaks group", required: false, defaultValue: "Everywhere"
        input name: "defaultVolume", type: "number", title: "Default volume 0-100", required: false, defaultValue: 80, range: "0..100"
        input name: "logEnable", type: "bool", title: "Enable debug logging", required: false, defaultValue: true
    }
}

void installed() {
    initialize()
}

void updated() {
    initialize()
}

void initialize() {
    if (state.volume == null) {
        state.volume = configuredDefaultVolume()
    }
    sendEvent(name: "volume", value: state.volume, unit: "%")
    sendEvent(name: "mute", value: state.volume == 0 ? "muted" : "unmuted")
    sendEvent(name: "lastStatus", value: "initialized")
}

void speak(message) {
    sendAnnouncement(message?.toString(), defaultGroup ?: "Everywhere", currentVolume())
}

void speak(String message) {
    sendAnnouncement(message, defaultGroup ?: "Everywhere", currentVolume())
}

void speak(String message, BigDecimal volume) {
    sendAnnouncement(message, defaultGroup ?: "Everywhere", volume)
}

void speak(String message, Integer volume) {
    sendAnnouncement(message, defaultGroup ?: "Everywhere", volume)
}

void speak(String message, BigDecimal volume, String voice) {
    sendAnnouncement(message, defaultGroup ?: "Everywhere", volume)
}

void speak(String message, Integer volume, String voice) {
    sendAnnouncement(message, defaultGroup ?: "Everywhere", volume)
}

void sendAnnouncement(String message, String group = null, volume = null) {
    speakToGroup(message, group ?: defaultGroup ?: "Everywhere", volume != null ? volume : currentVolume())
}

void speakToGroup(String message, String group, volume = null) {
    if (!message?.trim()) {
        sendEvent(name: "lastStatus", value: "empty message")
        return
    }

    Integer boundedVolume = normalizeVolume(volume != null ? volume : currentVolume())
    Map payload = [
        message: message,
        group: group ?: defaultGroup ?: "Everywhere",
        volume: boundedVolume
    ]

    Map params = [
        uri: normalizedBaseUrl(),
        path: "/api/services/ha_speaks/announce",
        requestContentType: "application/json",
        contentType: "application/json",
        headers: [
            Authorization: "Bearer ${haToken}"
        ],
        body: payload,
        timeout: 15
    ]

    if (logEnable) {
        log.debug "Sending HA Speaks announcement to ${payload.group} at volume ${payload.volume}"
    }

    asynchttpPost("handleHaResponse", params, [message: message, group: payload.group])
}

void handleHaResponse(resp, Map data) {
    Integer status = resp?.status ?: 0
    if (status >= 200 && status < 300) {
        sendEvent(name: "lastMessage", value: data.message)
        sendEvent(name: "lastGroup", value: data.group)
        sendEvent(name: "lastStatus", value: "ok ${status}")
        sendEvent(name: "speech", value: data.message)
        if (logEnable) {
            log.debug "HA Speaks announcement accepted: ${status}"
        }
        return
    }

    String errorText = resp?.errorMessage ?: resp?.data ?: "unknown error"
    sendEvent(name: "lastStatus", value: "error ${status}")
    log.warn "HA Speaks request failed: ${status} ${errorText}"
}

private String normalizedBaseUrl() {
    String value = haBaseUrl ?: ""
    return value.endsWith("/") ? value[0..-2] : value
}

private Integer normalizeVolume(value) {
    Integer volume = value as Integer
    if (volume < 0) {
        return 0
    }
    if (volume > 100) {
        return 100
    }
    return volume
}

void setVolume(volume) {
    Integer boundedVolume = normalizeVolume(volume)
    state.volume = boundedVolume
    sendEvent(name: "volume", value: boundedVolume, unit: "%")
    sendEvent(name: "mute", value: boundedVolume == 0 ? "muted" : "unmuted")
    sendEvent(name: "lastStatus", value: "volume set ${boundedVolume}")
}

void volumeUp() {
    setVolume(currentVolume() + 5)
}

void volumeDown() {
    setVolume(currentVolume() - 5)
}

void mute() {
    state.preMuteVolume = currentVolume()
    setVolume(0)
}

void unmute() {
    setVolume(state.preMuteVolume != null ? state.preMuteVolume : configuredDefaultVolume())
}

private Integer currentVolume() {
    return normalizeVolume(state.volume != null ? state.volume : configuredDefaultVolume())
}

private Integer configuredDefaultVolume() {
    return normalizeVolume(defaultVolume != null ? defaultVolume : 80)
}
