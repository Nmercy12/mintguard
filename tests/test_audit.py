"""Offline unit tests for MintGuard. No network access.

Run: python3 -m unittest discover -s tests -v
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mintguard.audit import classify_track, count_transient  # noqa: E402
from mintguard.keccak import keccak_256, selector  # noqa: E402


class TestKeccak(unittest.TestCase):
    def test_empty_vector(self):
        self.assertEqual(
            keccak_256(b"").hex(),
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")

    def test_known_selectors(self):
        self.assertEqual(selector("owner()"), "0x8da5cb5b")
        self.assertEqual(selector("totalSupply()"), "0x18160ddd")
        self.assertEqual(selector("balanceOf(address)"), "0x70a08231")
        self.assertEqual(selector("transfer(address,uint256)"), "0xa9059cbb")
        self.assertEqual(selector("mintPrice()"), "0x6817c76c")


class TestTransientScan(unittest.TestCase):
    def test_clean_code(self):
        # PUSH1 0x5c must NOT be counted (it is data, not an opcode).
        code = "0x60015c5d"  # PUSH1 0x01, TSTORE, TLOAD
        tstore, tload, size = count_transient(code)
        self.assertEqual((tstore, tload), (1, 1))
        self.assertEqual(size, 4)

    def test_push_data_ignored(self):
        # PUSH2 0x5c5d: both bytes are data, zero real opcodes.
        code = "0x615c5d00"
        tstore, tload, _ = count_transient(code)
        self.assertEqual((tstore, tload), (0, 0))

    def test_empty(self):
        self.assertEqual(count_transient("0x"), (0, 0, 0))
        self.assertEqual(count_transient(""), (0, 0, 0))


class TestClassify(unittest.TestCase):
    def test_nft_mint(self):
        self.assertEqual(
            classify_track(["mint", "ownerOf", "tokenURI", "totalSupply"], True),
            "nft_mint")

    def test_token(self):
        self.assertEqual(
            classify_track(["transfer", "balanceOf", "totalSupply"], False),
            "token")

    def test_mining(self):
        self.assertEqual(
            classify_track(["activate", "claim", "pendingReward", "nft"], False),
            "mining")

    def test_unknown(self):
        self.assertEqual(classify_track([], False), "unknown")


if __name__ == "__main__":
    unittest.main()
