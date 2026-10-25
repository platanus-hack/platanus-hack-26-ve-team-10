"""La foto de la tarjeta sobrevive a la copia que la hizo. Sin red ni bucket de verdad.

Correr desde services/api: .venv/bin/python -m unittest discover -s tests
"""

import unittest
from unittest import mock

from app.agents import card_image

TITLE = "iPhone 15 128 GB"
PHOTO = b"\xff\xd8\xff" + b"foto" * 600


class FakeBlob:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def exists(self):
        return self._name in self._store

    def download_as_bytes(self):
        return self._store[self._name]

    def upload_from_string(self, data, content_type=None):
        self._store[self._name] = data


class FakeBucket:
    """El bucket que comparten todas las copias: un diccionario que nadie reinicia."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def blob(self, name):
        return FakeBlob(self.objects, name)


class CardImageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bucket = FakeBucket()
        card_image._store.clear()
        card_image._bucket = self.bucket
        self.env = mock.patch.dict("os.environ", {"PUBLIC_BASE_URL": "https://api.usaprais.com"})
        self.env.start()
        # La búsqueda de la foto es lo caro: cuenta cuántas veces se llama de verdad.
        self.searches = 0

        async def fake_photo(title):
            self.searches += 1
            return PHOTO

        self.photo = mock.patch.object(card_image, "_product_photo", fake_photo)
        self.photo.start()
        self.stamp = mock.patch.object(card_image, "_stamp", lambda image: PHOTO)
        self.stamp.start()
        self.open = mock.patch.object(card_image.Image, "open", lambda data: data)
        self.open.start()

    def tearDown(self):
        for patch in (self.env, self.photo, self.stamp, self.open):
            patch.stop()
        card_image._bucket = card_image._UNSET
        card_image._store.clear()

    def _token(self, url):
        return url.rsplit("/", 1)[1].removesuffix(".jpg")

    async def test_the_same_product_always_gets_the_same_name(self):
        url = await card_image.marked_product_image(TITLE)
        again = await card_image.marked_product_image("  IPHONE   15   128 gb ")
        self.assertEqual(url, again)
        self.assertTrue(card_image.TOKEN.fullmatch(self._token(url)))

    async def test_another_copy_serves_the_photo_it_never_made(self):
        url = await card_image.marked_product_image(TITLE)
        card_image._store.clear()  # otra copia de prais-api: su memoria está vacía
        self.assertEqual(await card_image.read_card_image(self._token(url)), PHOTO)

    async def test_another_copy_does_not_search_the_photo_again(self):
        url = await card_image.marked_product_image(TITLE)
        card_image._store.clear()
        self.assertEqual(await card_image.marked_product_image(TITLE), url)
        self.assertEqual(self.searches, 1)

    async def test_the_photo_outlives_the_local_cache(self):
        url = await card_image.marked_product_image(TITLE)
        for number in range(card_image._LOCAL_MAX + 5):  # la memoria bota lo viejo; el bucket no
            await card_image.marked_product_image(f"producto {number}")
        self.assertNotIn(self._token(url), card_image._store)
        self.assertEqual(await card_image.read_card_image(self._token(url)), PHOTO)

    async def test_a_token_that_is_not_a_token_never_reaches_the_bucket(self):
        self.assertIsNone(await card_image.read_card_image("../../etc/passwd"))
        self.assertIsNone(await card_image.read_card_image("no-existe"))

    async def test_without_a_bucket_it_still_works_in_this_copy(self):
        card_image._bucket = None
        url = await card_image.marked_product_image(TITLE)
        self.assertEqual(await card_image.read_card_image(self._token(url)), PHOTO)
        self.assertEqual(self.bucket.objects, {})

    async def test_without_a_public_url_there_is_no_photo(self):
        with mock.patch.dict("os.environ", {"PUBLIC_BASE_URL": "", "SELF_URL": ""}):
            self.assertIsNone(await card_image.marked_product_image(TITLE))


if __name__ == "__main__":
    unittest.main()
