"""reelsmith: turn an app into a narrated demo video, all local."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Read from the installed package, so the CLI can never report a
    # different version from the one pyproject.toml was built with.
    __version__ = version("reelsmith")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0+unknown"
