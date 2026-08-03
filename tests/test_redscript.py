from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.models import Artifact, Reference
from cp77compat.redscript import (
    build_redscript_coverage,
    compare_redscript_references,
    parse_redscript_documents,
)


def artifact(path: Path, mod: str = "Example") -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=rf"r6\scripts\{mod}\{path.name}",
        extension=".reds",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state="deployed",
    )


class RedscriptTests(unittest.TestCase):
    def test_extracts_full_method_signatures_fields_and_wrapper_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.reds"
            path.write_text(
                """module Example
// @replaceMethod(Fake) func Ignored() -> Void {}
@wrapMethod(PlayerPuppet)
@if(ModuleExists(\"Example\"))
protected cb func OnEvent(opt evt: ref<Event>, out values: [Int32]) -> Void {
  return wrappedMethod(evt, values);
}

@addField(PlayerPuppet) private let exampleField: ref<ExampleData>;
@addMethod(PlayerPuppet)
public func Example(value: array<ref<Item>>) -> Bool { return true; }
@wrapMethod(PlayerPuppet)
public func IsReady() -> Bool = wrappedMethod();
""",
                encoding="utf-8",
            )
            documents, references, findings = parse_redscript_documents([artifact(path)])
            self.assertEqual([], findings)
            self.assertEqual(4, len(references))
            wrapper = next(
                item for item in references
                if item.identity.startswith("PlayerPuppet.OnEvent")
            )
            self.assertEqual(
                "PlayerPuppet.OnEvent(ref<Event>,array<Int32>)->Bool",
                wrapper.identity,
            )
            self.assertEqual(3, wrapper.line)
            self.assertEqual(5, wrapper.details["declaration_line"])
            self.assertTrue(wrapper.details["calls_wrapped_method"])
            self.assertTrue(wrapper.details["condition_state"])
            field = next(item for item in references if item.kind == "field.add")
            self.assertEqual("PlayerPuppet.exampleField", field.identity)
            self.assertEqual("ref<ExampleData>", field.details["field_type"])
            expression_wrapper = next(
                item for item in references
                if item.identity == "PlayerPuppet.IsReady()->Bool"
            )
            self.assertTrue(expression_wrapper.details["calls_wrapped_method"])
            coverage = build_redscript_coverage(documents, references)
            self.assertEqual(1, coverage["documents"])
            self.assertEqual(2, coverage["annotation_operations"][0]["wrap_methods"])

    def test_comparison_classifies_replacements_added_symbols_and_wrappers(self) -> None:
        def method(kind: str, mod: str, body: str, calls: int = 1) -> Reference:
            return Reference(
                "redscript",
                kind,
                "Target.DoThing(Int32)->Bool",
                mod,
                f"{mod}.reds",
                1,
                {
                    "body_fingerprint": body,
                    "calls_wrapped_method": calls > 0,
                    "wrapped_method_calls": calls,
                },
            )

        findings = compare_redscript_references([
            method("method.replace", "A", "one"),
            method("method.replace", "B", "two"),
            method("method.wrap", "A", "wrap", 0),
            method("method.wrap", "B", "wrap2"),
        ])
        rules = {item.rule_id for item in findings}
        self.assertIn("RS-METHOD-REPLACEMENT-CONFLICT", rules)
        self.assertIn("RS-WRAPPER-SKIPS-WRAPPED-METHOD", rules)
        self.assertIn("RS-WRAPPER-CHAIN-TERMINATED", rules)

        findings = compare_redscript_references([
            method("method.wrap", "A", "wrap"),
            method("method.wrap", "B", "wrap2"),
        ])
        self.assertEqual("RS-WRAPPER-CHAIN", findings[0].rule_id)

        findings = compare_redscript_references([
            method("method.replace", "A", "same"),
            method("method.replace", "B", "same"),
        ])
        self.assertEqual("RS-METHOD-REPLACEMENT-DUPLICATE", findings[0].rule_id)

        fields = [
            Reference("redscript", "field.add", "Target.value", mod, f"{mod}.reds", 1,
                      {"field_type": typ})
            for mod, typ in (("A", "Int32"), ("B", "String"))
        ]
        self.assertEqual(
            "RS-ADDED-FIELD-CONFLICT",
            compare_redscript_references(fields)[0].rule_id,
        )


if __name__ == "__main__":
    unittest.main()
