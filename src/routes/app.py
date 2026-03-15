"""
app.py — Flask application factory.

Creates the Flask app and registers all route blueprints.
Import ``create_app()`` from here; do not instantiate Flask anywhere else.
"""

import os
from flask import Flask

from src.paths import _MEIPASS


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns a fully wired Flask instance ready to be handed to
    ``app.run()`` or the pywebview thread.
    """
    template_folder = os.path.join(_MEIPASS, "templates")
    static_folder   = os.path.join(_MEIPASS, "static")
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

    _register_blueprints(app)

    return app


def _register_blueprints(app: Flask) -> None:
    """Import and register every route blueprint."""
    import src.routes.main as _routes_main
    import src.routes.tasks as _routes_tasks
    import src.routes.extras as _routes_extras
    import src.routes.updates as _routes_updates
    import src.routes.hardware as _routes_hardware
    import src.routes.system as _routes_system

    app.register_blueprint(_routes_main.bp)
    app.register_blueprint(_routes_tasks.bp)
    app.register_blueprint(_routes_extras.bp)
    app.register_blueprint(_routes_updates.bp)
    app.register_blueprint(_routes_hardware.bp)
    app.register_blueprint(_routes_system.bp)
