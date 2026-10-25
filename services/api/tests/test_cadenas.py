"""La lista de cadenas se compara por dominio exacto, sin red."""

import unittest

from app.lib.cadenas import CHAINS, REVIEWED_ON, chain_for_host


class ChainListTests(unittest.TestCase):
    def test_every_chain_is_an_own_store_reviewed_the_same_day(self):
        self.assertGreater(len(CHAINS), 0)
        for chain in CHAINS:
            self.assertTrue(chain.tienda_propia)
            self.assertEqual(chain.reviewed_on, REVIEWED_ON)
            self.assertTrue(chain.url.startswith("https://"))

    def test_price_sources_are_the_four_online_stores(self):
        picked = {chain.name for chain in CHAINS if chain.price_source}
        self.assertEqual(picked, {"Gama", "IVOO", "Daka", "EPA"})
        for chain in CHAINS:
            if chain.price_source:
                self.assertTrue(chain.online_store)
                self.assertFalse(chain.blocks_http_clients)

    def test_www_matches_and_a_lookalike_or_other_subdomain_does_not(self):
        self.assertEqual(chain_for_host("https://www.farmatodo.com.ve/x").name, "Farmatodo")
        self.assertEqual(chain_for_host("FARMAtodo.com.ve").name, "Farmatodo")
        self.assertEqual(chain_for_host("https://tiendasdaka.com/ve").name, "Daka")
        self.assertIsNone(chain_for_host("https://tiendas-daka.com"))
        self.assertEqual(chain_for_host("https://ve.epaenlinea.com/p").name, "EPA")
        self.assertIsNone(chain_for_host("https://epaenlinea.com"))
        self.assertIsNone(chain_for_host("https://cr.epaenlinea.com"))
        self.assertEqual(chain_for_host("www.multimax.com.ve").name, "Multimax")
        self.assertIsNone(chain_for_host("https://www.multimax.net"))
        self.assertEqual(chain_for_host("https://www.sambilonline.com").name, "Sambil")
        self.assertEqual(chain_for_host("asistentesambil.com").name, "Sambil")
        self.assertIsNone(chain_for_host(""))
        self.assertIsNone(chain_for_host("https://farmavenezuela.com"))
