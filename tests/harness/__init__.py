"""Test harness shared by conftest and the replay/degraded-mode tests."""


class NetworkBlocked(RuntimeError):
    """A test reached for the network without an explicit mock transport."""
