from apscheduler import AsyncScheduler
from fastapi import Request


def get_scheduler(request: Request) -> AsyncScheduler:
    return request.app.state.scheduler
