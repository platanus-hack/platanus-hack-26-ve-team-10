"""El diálogo a medias, en memoria y en sqlite. Sin red.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import tempfile
import unittest

from sqlalchemy.ext.asyncio import create_async_engine

from app.lib.dialog import TTL_SECONDS, MemoryDialogStore, SqlDialogStore

PENDING = {"pending": {"product": "iPhone 14", "closed": [], "family": "iphone 14"}}
BUTTONS = {"product": "MacBook Air M5", "actions": {"Solo nuevos": "MacBook Air M5 nuevo"}}


class DialogStoreTests:
    """Las mismas reglas para las dos implementaciones."""

    async def test_an_unknown_person_has_no_dialog(self) -> None:
        self.assertEqual(await self.store.load("nadie"), {})

    async def test_it_reads_back_what_another_copy_saved(self) -> None:
        await self.store.save("whatsapp:5801", PENDING)
        self.assertEqual(await self.store.load("whatsapp:5801"), PENDING)

    async def test_saving_again_replaces_the_whole_state(self) -> None:
        await self.store.save("whatsapp:5801", PENDING)
        await self.store.save("whatsapp:5801", BUTTONS)
        # Tras buscar ya no hay pregunta abierta: el estado se reemplaza, no se mezcla.
        self.assertEqual(await self.store.load("whatsapp:5801"), BUTTONS)

    async def test_dropping_forgets_only_that_person(self) -> None:
        await self.store.save("whatsapp:5801", PENDING)
        await self.store.save("whatsapp:5802", BUTTONS)
        await self.store.drop("whatsapp:5801")
        self.assertEqual(await self.store.load("whatsapp:5801"), {})
        self.assertEqual(await self.store.load("whatsapp:5802"), BUTTONS)


class MemoryDialogTests(DialogStoreTests, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = MemoryDialogStore()

    async def test_a_dialog_older_than_the_window_is_gone(self) -> None:
        await self.store.save("whatsapp:5801", BUTTONS)
        state, saved_at = self.store._rows["whatsapp:5801"]
        self.store._rows["whatsapp:5801"] = (state, saved_at - TTL_SECONDS - 1)
        # WhatsApp solo deja contestar libre 24 horas: un toque rezagado no
        # revive el producto de anteayer.
        self.assertEqual(await self.store.load("whatsapp:5801"), {})


class SqlDialogTests(DialogStoreTests, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._tmp.name}/dialog.db")
        self.store = SqlDialogStore(self.engine)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self._tmp.cleanup()

    async def test_two_copies_of_the_api_share_the_same_row(self) -> None:
        other = SqlDialogStore(self.engine)
        await self.store.save("whatsapp:5801", PENDING)
        # La pregunta sale de una copia de prais-api y el toque entra por otra.
        self.assertEqual(await other.load("whatsapp:5801"), PENDING)
        await other.save("whatsapp:5801", BUTTONS)
        self.assertEqual(await self.store.load("whatsapp:5801"), BUTTONS)

    async def test_clear_empties_the_table(self) -> None:
        await self.store.save("whatsapp:5801", PENDING)
        await self.store.clear()
        self.assertEqual(await self.store.load("whatsapp:5801"), {})


if __name__ == "__main__":
    unittest.main()
