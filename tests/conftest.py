import logging
import pytest


# Suppress the ConjunctiveGraph deprecation warning from rocrate_validator
class ConjunctiveGraphFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return not (
            "ConjunctiveGraph is deprecated" in message
            or "Consider reporting this as a bug" in message
        )


@pytest.fixture(scope="session", autouse=True)
def suppress_rocrate_warnings():
    logger = logging.getLogger("rocrate_validator.models")
    logger.addFilter(ConjunctiveGraphFilter())

# TODO write pytest tests that run the python code blocks in README.md
