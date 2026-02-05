import sys
from importlib.metadata import version

from packaging.specifiers import SpecifierSet
from packaging.version import Version

import backoff

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def test_version():
    assert version("python-backoff") == backoff.__version__, (
        f"Version in __init__.py ({backoff.__version__}) does not match version in pyproject.toml ({version('python-backoff')})"
    )


def test_python_classifiers():
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    versions = map(
        lambda x: Version(x.split(" :: ")[-1]),
        filter(
            lambda x: x.startswith("Programming Language :: Python :: 3."),
            data["project"]["classifiers"],
        ),
    )
    requires_python = SpecifierSet(data["project"]["requires-python"])
    assert all(v in requires_python for v in versions)
