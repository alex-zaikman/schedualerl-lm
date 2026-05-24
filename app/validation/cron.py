from cron_validator import CronValidator


def is_valid_cron_expression(expression: str) -> bool:
    try:
        return CronValidator.parse(expression) is not None
    except ValueError:
        return False
