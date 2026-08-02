from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from cp77compat.tweakdb import build_tweakdb_record_index


class TweakDBRecordIndexTests(unittest.TestCase):
    def test_indexes_named_and_generated_inline_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            source = game / "tools" / "redmod" / "tweaks" / "base" / "items.tweak"
            source.parent.mkdir(parents=True)
            source.write_text(
                """package Items

BaseItem : Item
{
    String text = "a brace { inside a string";
}

/* Hidden : Item
{
}
*/
Standalone
{
}
""",
                encoding="utf-8",
            )
            inline = "Items.BaseItem_inline0"
            encoded = inline.encode("utf-8")
            tweakdb_id = struct.pack(
                "<IB3x",
                zlib.crc32(encoded),
                len(encoded),
            )
            binary = game / "r6" / "cache" / "tweakdb.bin"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"prefix" + tweakdb_id + b"suffix")

            index = build_tweakdb_record_index(game)

            self.assertEqual(1, index.source_files)
            self.assertTrue(index.contains("Items.BaseItem"))
            self.assertTrue(index.contains("Items.Standalone"))
            self.assertTrue(index.contains(inline))
            self.assertFalse(index.contains("Items.Hidden"))
            self.assertFalse(index.contains("Items.Missing_inline0"))


if __name__ == "__main__":
    unittest.main()
