"""La fábrica de sesiones elige memoria o base de datos según la URL. Sin red."""

import asyncio
import os
import tempfile
import unittest

from google.adk.sessions import DatabaseSessionService, InMemorySessionService

from app import runtime
from app.agent import build_app


class SessionServiceTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("SESSION_DATABASE_URL", None)
        runtime.reset()

    def test_memory_when_url_is_missing(self) -> None:
        os.environ.pop("SESSION_DATABASE_URL", None)
        runtime.reset()
        self.assertIsInstance(runtime.session_service(), InMemorySessionService)

    def test_database_when_url_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["SESSION_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp}/sessions.db"
            runtime.reset()
            try:
                self.assertIsInstance(runtime.session_service(), DatabaseSessionService)
            finally:
                db = runtime.engine()
                if db is not None:
                    asyncio.run(db.dispose())

    def test_compaction_keeps_the_price_facts(self) -> None:
        config = build_app().events_compaction_config
        assert config is not None
        self.assertEqual(config.compaction_interval, 4)
        self.assertEqual(config.overlap_size, 1)
        self.assertEqual(config.token_threshold, 4000)
        self.assertEqual(config.event_retention_size, 8)
        prompt = config.summarizer._prompt_template
        self.assertIn("{conversation_history}", prompt)
        self.assertIn("precio", prompt)
