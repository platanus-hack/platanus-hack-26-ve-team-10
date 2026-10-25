"""La tasa oficial del BCV con un cliente HTTP falso: sin red.

Correr desde apps/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest
from unittest import mock

from app.lib import rate

OFICIAL = b'{"moneda":"USD","fuente":"oficial","nombre":"D\\u00f3lar","compra":null,"venta":null,"promedio":886.2271,"fechaActualizacion":"2026-10-23T00:00:00-04:00"}'


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class FakeClient:
    """Devuelve lo que le den, o lo lanza si es una excepción. Cuenta los pedidos."""

    calls = 0

    def __init__(self, answer):
        self.answer = answer

    def __call__(self, *, timeout):
        assert timeout > 0
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url):
        assert url == rate.RATE_URL
        type(self).calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return FakeResponse(self.answer)


class RateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        rate._cached, rate._until = rate.SEED, 0.0
        FakeClient.calls = 0

    def answering(self, answer):
        return mock.patch.object(rate, "httpx", mock.Mock(AsyncClient=FakeClient(answer)))

    async def test_reads_the_published_rate(self):
        with self.answering(OFICIAL):
            tasa = await rate.get_rate()
        self.assertEqual(tasa.source, "tasa oficial del BCV")
        self.assertEqual(tasa.usd_to_ves, 886.2271)
        self.assertEqual(tasa.observed_at, "2026-10-23T00:00:00-04:00")

    async def test_does_not_ask_again_while_the_cache_lasts(self):
        with self.answering(OFICIAL):
            first = await rate.get_rate()
            second = await rate.get_rate()
        self.assertEqual(FakeClient.calls, 1)
        self.assertEqual(first, second)

    async def test_keeps_the_last_good_rate_when_the_api_fails(self):
        with self.answering(OFICIAL):
            good = await rate.get_rate()
        rate._until = 0.0
        with self.answering(RuntimeError("dolarapi caído")):
            tasa = await rate.get_rate()
        self.assertEqual(tasa, good)

    async def test_falls_back_to_the_seed_and_waits_before_retrying(self):
        with self.answering(RuntimeError("dolarapi caído")):
            tasa = await rate.get_rate()
            await rate.get_rate()
        self.assertEqual(tasa, rate.SEED)
        # Un solo pedido: con la API caída, una búsqueda no espera el timeout cada vez.
        self.assertEqual(FakeClient.calls, 1)

    async def test_rejects_a_rate_that_would_break_the_conversion(self):
        with self.answering(b'{"promedio":0,"fechaActualizacion":"2026-10-23T00:00:00-04:00"}'):
            tasa = await rate.get_rate()
        self.assertEqual(tasa, rate.SEED)

    async def test_rejects_an_answer_with_another_shape(self):
        with self.answering(b'{"error":"not found"}'):
            tasa = await rate.get_rate()
        self.assertEqual(tasa, rate.SEED)
