"""A second launch can raise the existing workspace without starting another recorder."""

import hashlib
from collections.abc import Callable
from pathlib import Path

from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name(config: Path) -> str:
    return (
        "LocalPhraser-" + hashlib.sha256(str(config.resolve()).casefold().encode()).hexdigest()[:24]
    )


def activate_existing(config: Path) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name(config))
    if not socket.waitForConnected(500):
        return False
    socket.disconnectFromServer()
    return True


def listen(config: Path, show: Callable[[], None]) -> QLocalServer:
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

    def connected() -> None:
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket is not None:
                # A connection only raises this app; no arbitrary commands or paths are accepted.
                show()
                socket.disconnectFromServer()
                socket.deleteLater()

    server.newConnection.connect(connected)
    if not server.listen(server_name(config)):
        raise OSError("The desktop activation channel is unavailable")
    return server
