"""The driving side of the hexagon: HTTP, WebSocket, and the composition root.

The simulation is synchronous and knows nothing about sockets. Everything asyncio
lives here: the tick loop in :mod:`age.presentation.room`, the per-connection write
queues in :mod:`age.presentation.connection`, and the adapters that turn frames into
queued commands.
"""
