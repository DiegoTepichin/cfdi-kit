from pathlib import Path

import pytest

from cfdi_kit.models import Cfdi
from cfdi_kit.parser import parse_file

FIXTURES = Path(__file__).parent / "fixtures"
MY_RFC = "CACX7605101P8"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def load(name: str) -> Cfdi:
    return parse_file(FIXTURES / name)


@pytest.fixture
def all_valid() -> list[Cfdi]:
    return [parse_file(p) for p in sorted(FIXTURES.glob("*.xml"))]
