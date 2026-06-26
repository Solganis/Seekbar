from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_SINGLE_INSTANCE_KEY = "seekbar-single-instance"


class _SingleInstanceGuard(QObject):
    activated = Signal()

    def __init__(self, key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server: QLocalServer | None = None

    def is_primary(self) -> bool:
        probe = QLocalSocket()
        probe.connectToServer(self._key)
        if probe.waitForConnected(200):
            probe.write(b"show")
            probe.flush()
            probe.waitForBytesWritten(200)
            probe.disconnectFromServer()
            return False
        QLocalServer.removeServer(self._key)  # clear a stale socket left by a crashed instance (Unix)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(self._key)
        return True

    def _on_new_connection(self) -> None:
        server = self._server
        if server is not None:
            connection = server.nextPendingConnection()
            if connection is not None:
                connection.close()
        self.activated.emit()
