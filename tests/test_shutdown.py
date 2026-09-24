"""Shutdown behaviour: a stop signal must actually close the Discord gateway.

The bug this guards against: `main()` used to call `await client.start(token)`
bare. discord.py's `start()` runs the gateway loop forever and never calls
`close()` on its own. When the process is killed, the websocket is dropped
without a close frame and Discord keeps showing the bot as online.

Two distinct stop paths matter:
- SIGINT  (Ctrl+C in a terminal)
- SIGTERM (what `systemctl stop` sends; the Pi daemons depend on this)

A `try/except KeyboardInterrupt` around `client.start()` only covers the first
one, and even then only if the interpreter happens to unwind it. These tests pin
both, plus the guarantee that start-up failures still surface.
"""

import asyncio
import signal
from types import SimpleNamespace

import pytest

import main as main_module


class FakeClient:
    """Minimal stand-in that records whether it was closed cleanly."""

    def __init__(self, *, raise_on_start=None, start_returns=False):
        self.entered = False
        self.exited = False
        self.closed = False
        self.started = False
        self.setup_hook = None
        self._raise_on_start = raise_on_start
        self._start_returns = start_returns
        self._stop = asyncio.Event()

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        # Mirror discord.py: __aexit__ closes if not already closing.
        if not self.closed:
            await self.close()

    async def start(self, token, *, reconnect=True):
        self.started = True
        if self._raise_on_start is not None:
            raise self._raise_on_start
        if self._start_returns:
            return
        # Behave like the real gateway loop: never return until cancelled.
        await self._stop.wait()

    async def close(self):
        self.closed = True
        self._stop.set()


class TestRunBot:
    """Direct tests of run_bot() with an injected stop event."""

    def test_stop_event_closes_the_gateway(self):
        client = FakeClient()

        async def scenario():
            stop = asyncio.Event()
            task = asyncio.create_task(main_module.run_bot(client, "tok", stop_event=stop))
            await asyncio.sleep(0.05)
            assert client.entered and client.started
            assert not client.exited, "should still be running"
            stop.set()  # this is what the signal handler does
            await asyncio.wait_for(task, timeout=5)

        asyncio.run(scenario())

        assert client.exited, "client context manager was never exited"
        assert client.closed, "stop signal did NOT close the gateway connection"

    def test_startup_error_propagates_but_still_closes(self):
        client = FakeClient(raise_on_start=RuntimeError("bad token"))

        with pytest.raises(RuntimeError, match="bad token"):
            asyncio.run(main_module.run_bot(client, "tok", stop_event=asyncio.Event()))

        assert client.closed, "no socket should be leaked on a failed start"

    def test_start_returning_normally_closes(self):
        client = FakeClient(start_returns=True)
        asyncio.run(main_module.run_bot(client, "tok", stop_event=asyncio.Event()))
        assert client.closed


class TestSignalHandlers:
    """The real signal handlers must be registered for both stop signals."""

    def test_sigint_and_sigterm_both_trigger_shutdown(self, monkeypatch):
        """Whatever the OS sends, run_bot must unwind through close()."""
        registered = {}

        class FakeLoop:
            def add_signal_handler(self, sig, callback):
                registered[sig] = callback

            def remove_signal_handler(self, sig):
                registered.pop(sig, None)

        client = FakeClient()
        real_get_loop = asyncio.get_running_loop

        async def scenario():
            task = asyncio.create_task(main_module.run_bot(client, "tok"))
            # The handler registration happens inside the coroutine; wait for it.
            for _ in range(100):
                if signal.SIGINT in registered:
                    break
                await asyncio.sleep(0.01)

            assert signal.SIGINT in registered, "SIGINT (Ctrl+C) handler not installed"
            assert signal.SIGTERM in registered, "SIGTERM (systemctl stop) handler not installed"

            # Fire the SIGTERM handler, i.e. what `systemctl stop` does.
            registered[signal.SIGTERM]()
            await asyncio.wait_for(task, timeout=5)

        monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeLoop())
        try:
            asyncio.run(scenario())
        finally:
            monkeypatch.setattr(asyncio, "get_running_loop", real_get_loop)

        assert client.closed, "SIGTERM (systemctl stop) did NOT close the gateway"


class TestMainWiring:
    """main() must delegate to run_bot, not call client.start() bare."""

    @pytest.fixture
    def patched(self, monkeypatch):
        calls = {}
        client = FakeClient()

        async def fake_run_bot(client_arg, token, **kwargs):
            calls["client"] = client_arg
            calls["token"] = token
            async with client_arg:
                pass

        bot = SimpleNamespace(token="unit-test-token", client=client)  # noqa: S106
        monkeypatch.setattr(main_module.config, "BOT_TOKEN", "unit-test-token")
        monkeypatch.setattr(main_module.config, "CHAT_CHANNEL", "general")
        monkeypatch.setattr(main_module.config, "DEFAULT_PERSONALITY", "tama")
        monkeypatch.setattr(main_module.config, "HOME", "/nonexistent/xedb-test-home")
        monkeypatch.setattr(main_module, "PERSONALITIES", {"tama": object()})
        monkeypatch.setattr(main_module, "ENABLED_EXTENSIONS", [])
        monkeypatch.setattr(main_module, "EchoBot", lambda **kwargs: bot)
        monkeypatch.setattr(main_module, "run_bot", fake_run_bot)
        return calls, client

    def test_main_runs_the_bot_through_run_bot(self, patched):
        calls, client = patched
        asyncio.run(main_module.main())
        assert calls["client"] is client
        assert calls["token"] == "unit-test-token"
        assert client.closed
