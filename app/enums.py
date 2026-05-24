from enum import StrEnum


class TriggerType(StrEnum):
    ONCE = "once"
    CRON = "cron"
    INTERVAL = "interval"


class HealthStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
