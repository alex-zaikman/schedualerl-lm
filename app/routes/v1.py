from fastapi import APIRouter

from app.auth.dependencies import protected_dependencies
from app.routes.api import router as api_router
from app.routes.tasks import router as tasks_router
from app.routes.trigger_parse import router as trigger_parse_router

router = APIRouter(dependencies=protected_dependencies)
router.include_router(api_router)
router.include_router(tasks_router)
router.include_router(trigger_parse_router)
