from sqlalchemy import String, event
from sqlalchemy.orm import (
    Mapped,
    ORMExecuteState,
    Session,
    declared_attr,
    mapped_column,
    with_loader_criteria,
)


class UserOwned:
    """Mixin for models scoped to a user."""

    @declared_attr
    def user_id(cls) -> Mapped[str]:
        return mapped_column(String, nullable=False, index=True)


def register_row_scope_events() -> None:
    @event.listens_for(Session, "do_orm_execute")
    def _apply_user_scope(execute_state: ORMExecuteState) -> None:
        user_id = execute_state.session.info.get("current_user_id")
        if not user_id or not execute_state.is_select:
            return
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                UserOwned,
                lambda cls: cls.user_id == user_id,
                include_aliases=True,
            )
        )
