from enum import StrEnum


class TriggerType(StrEnum):
    ONCE = "once"
    CRON = "cron"
    INTERVAL = "interval"


class TaskSortField(StrEnum):
    CREATED_AT = "created_at"
    NEXT_RUN_AT = "next_run_at"
    UPDATED_AT = "updated_at"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class HealthStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class TaskHistoryEventType(StrEnum):
    TASK_CREATED = "task_created"
    TASK_ACTIVATED = "task_activated"
    TASK_DEACTIVATED = "task_deactivated"
    TASK_DELETED = "task_deleted"
    EXECUTION = "execution"


class ExecutionSource(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
