import pytest
import time_machine

from tests.constants import FROZEN_TIME


@pytest.fixture
def frozen_time():
    with time_machine.travel(FROZEN_TIME, tick=False) as traveller:
        yield traveller
