"""
webapi.py — pywebview JavaScript API bridge.

The ``WebAPI`` class is passed to ``webview.start()`` as ``js_api``.
Its public methods are callable from the frontend via ``window.pywebview.api.*``.

Keeping this class separate from the Flask app means:
- The pywebview dependency is isolated to one file.
- The log-window lifecycle logic is easy to find and modify.
- main.py stays clean — it just instantiates WebAPI and hands it to webview.
"""

import state


class WebAPI:
    """Methods callable from JS via ``pywebview.api.*``."""

    _log_win = None  # reference to the currently open log window (if any)

    def open_log(self) -> None:
        """Toggle the floating log window.

        - If no log window is open: create one positioned to the right of the
          main window.
        - If one is already open: close it.

        Falls back to a fixed-size window if the main window geometry cannot
        be read (e.g. older pywebview versions).
        """
        try:
            import webview

            # ── Close if already open ────────────────────────────────────
            if WebAPI._log_win is not None:
                try:
                    WebAPI._log_win.destroy()
                except Exception:
                    pass
                WebAPI._log_win = None
                state.push("log_window", {"open": False})
                return

            # ── Read main window geometry ────────────────────────────────
            x, y, w, h = 0, 0, 1200, 720
            try:
                wins = webview.windows
                if wins:
                    mw = wins[0]
                    x  = getattr(mw, "x",      0)    or 0
                    y  = getattr(mw, "y",      0)    or 0
                    w  = getattr(mw, "width",  1200) or 1200
                    h  = getattr(mw, "height", 720)  or 720
            except Exception:
                pass

            log_w = 480
            log_h = h
            log_x = x + w  # position to the right of the main window

            # ── Create log window ────────────────────────────────────────
            win = webview.create_window(
                title="Лог выполнения",
                url="http://127.0.0.1:5757/log",
                width=log_w,
                height=log_h,
                x=log_x,
                y=y,
                resizable=True,
                background_color="#00000000",
                transparent=True,
            )
            WebAPI._log_win = win

            def _on_closed() -> None:
                WebAPI._log_win = None
                state.push("log_window", {"open": False})

            try:
                win.events.closed += _on_closed
            except Exception:
                pass

            state.push("log_window", {"open": True})

        except Exception as e:
            # Fallback: open without geometry info (older pywebview / import error)
            print(f"[log window] {e}")
            self._open_log_fallback()

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _open_log_fallback(self) -> None:
        """Open the log window with fixed dimensions when geometry is unavailable."""
        try:
            import webview

            win = webview.create_window(
                title="Лог выполнения",
                url="http://127.0.0.1:5757/log",
                width=480,
                height=680,
                resizable=True,
                background_color="#0f1117",
            )
            WebAPI._log_win = win

            def _on_closed() -> None:
                WebAPI._log_win = None
                state.push("log_window", {"open": False})

            try:
                win.events.closed += _on_closed
            except Exception:
                pass

            state.push("log_window", {"open": True})

        except Exception as e2:
            print(f"[log window fallback] {e2}")
