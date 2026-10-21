"""Optional pytest plugin: -p app.tests.no_external_transport.

Local test transports/event-loop wakeups are allowed; external TCP connections
fail before any real broker or GPT transport can send an authenticated request.
"""
import ipaddress
import socket

_originals = {}


def _local(address):
    if not isinstance(address, tuple):
        return True  # Local Unix-domain sockets, where supported.
    host = address[0]
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def pytest_sessionstart(session):
    for name in ('connect', 'connect_ex'):
        original = getattr(socket.socket, name)
        _originals[name] = original
        def guarded(self, address, _original=original):
            if not _local(address):
                raise AssertionError('External transport forbidden in backend pytest')
            return _original(self, address)
        setattr(socket.socket, name, guarded)


def pytest_sessionfinish(session, exitstatus):
    for name, original in _originals.items():
        setattr(socket.socket, name, original)
    _originals.clear()
