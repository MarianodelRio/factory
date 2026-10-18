"""swfactory: a method and a CLI to build software with coding agents on Orca."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("swfactory")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0"
