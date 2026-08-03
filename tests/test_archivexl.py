from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.archives import parse_archive_list_output
from cp77compat.archivexl import (
    build_archivexl_coverage,
    compare_override_references,
    compare_quest_references,
    compare_references,
    compare_resource_references,
    parse_documents,
    resolve_archive_references,
    resolve_quest_references,
)
from cp77compat.archivexl_payload_analysis import (
    compare_customization_entries,
    compare_journal_entries,
    compare_factory_entries,
    compare_localization_entries,
    compare_patch_target_entries,
    parse_factory_payload,
    parse_customization_payload,
    parse_journal_payload,
    parse_localization_payload,
    parse_resource_patch_payload,
    validate_factory_targets,
)
from cp77compat.models import ArchiveManifest, ArchiveMember, Artifact, Reference


def artifact(path: Path, mod: str) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=r"archive\pc\mod\test.archive.xl",
        extension=".xl",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
    )


class ArchiveXLTests(unittest.TestCase):
    def test_extracts_customization_declarations_with_gender_and_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "customizations.xl"
            path.write_text(
                "customizations:\n  female:\n    - mod\\female.inkcharcustomization\n"
                "  male: mod\\male.inkcharcustomization\n",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], findings)
            self.assertEqual([3, 4], [item.line for item in references])
            self.assertEqual(["female", "male"], [item.details["gender"] for item in references])
            self.assertTrue(all(item.kind == "customization" for item in references))

    def test_parses_customization_groups_options_and_choices(self) -> None:
        declaration = Reference(
            "archivexl",
            "customization",
            r"mod\female.inkcharcustomization",
            "A",
            "a.xl",
            4,
            {"gender": "female"},
        )
        payload = {
            "Data": {
                "RootChunk": {
                    "$type": "gameuiCharacterCustomizationInfoResource",
                    "armsGroups": [],
                    "armsCustomizationOptions": [],
                    "bodyGroups": [],
                    "bodyCustomizationOptions": [],
                    "headGroups": [
                        {"name": {"$value": "TPP"}, "options": [{"$value": "hair_a"}]}
                    ],
                    "headCustomizationOptions": [
                        {
                            "Data": {
                                "$type": "gameuiSwitcherInfo",
                                "name": {"$value": "hairstyle"},
                                "uiSlot": {"$value": "hair"},
                                "options": [
                                    {
                                        "$type": "gameuiSwitcherOption",
                                        "localizedName": "Hair A",
                                        "names": [{"$value": "hair_a"}],
                                    }
                                ],
                            }
                        }
                    ],
                }
            }
        }
        references, findings = parse_customization_payload(
            declaration, payload, "a.archive"
        )
        self.assertEqual([], findings)
        self.assertEqual(
            {
                "female/head/group/TPP/hair_a",
                "female/head/name/hairstyle",
                "female/head/name/hairstyle/choice/Hair A",
            },
            {item.identity for item in references},
        )
        self.assertTrue(all(item.line == 4 for item in references))

    def test_customization_comparison_separates_composition_and_replacement(self) -> None:
        options = [
            Reference(
                "archivexl",
                "customization.option",
                "female/head/name/eyebrows",
                mod,
                f"{mod}.xl",
                details={
                    "option_type": "gameuiSwitcherInfo",
                    "metadata_fingerprint": "same",
                    "named": True,
                    "gender": "female",
                    "part": "head",
                },
            )
            for mod in ("A", "B")
        ]
        choices = [
            Reference(
                "archivexl",
                "customization.choice",
                "female/head/name/eyebrows/choice/shared",
                mod,
                f"{mod}.xl",
                details={"fingerprint": fingerprint},
            )
            for mod, fingerprint in (("A", "first"), ("B", "second"))
        ]
        findings, stats = compare_customization_entries([*options, *choices])
        self.assertEqual(
            {
                "AXL-CUSTOMIZATION-OPTION-COMPOSABLE",
                "AXL-CUSTOMIZATION-CHOICE-CONFLICT",
            },
            {item.rule_id for item in findings},
        )
        self.assertEqual(1, stats["composable_entries"])
        self.assertEqual(1, stats["conflicting_entries"])

    def test_customization_selector_overlap_honors_wildcards_not_empty_cnames(self) -> None:
        def option(mod: str, identity: str, slot: str) -> Reference:
            return Reference(
                "archivexl",
                "customization.option",
                identity,
                mod,
                f"{mod}.xl",
                details={
                    "named": False,
                    "gender": "female",
                    "part": "head",
                    "ui_slot": slot,
                    "link": "",
                    "option_type": "gameuiAppearanceInfo",
                    "metadata_fingerprint": mod,
                },
            )

        findings, stats = compare_customization_entries(
            [
                option("A", "female/head/selector/slot=eyes_color*", "eyes_color*"),
                option("B", "female/head/selector/slot=eyes_color", "eyes_color"),
                option("C", "female/head/selector/slot=hair_color", "hair_color"),
            ]
        )
        selector_findings = [
            item
            for item in findings
            if item.rule_id == "AXL-CUSTOMIZATION-SELECTOR-OVERLAP"
        ]
        self.assertEqual(1, len(selector_findings))
        self.assertEqual(["A", "B"], selector_findings[0].participants)
        self.assertEqual(1, stats["review_entries"])

    def test_extracts_override_tags_with_effective_masks_and_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "overrides.xl"
            path.write_text(
                """overrides:
  tags:
    HideChunks:
      body: {hide: [0, 2]}
    RawMask:
      decal: 15
    HideShorthand:
      garment: [1, 3]
""",
                encoding="utf-8",
            )
            documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], findings)
            self.assertEqual(3, len(references))
            hide = next(ref for ref in references if ref.identity == "HideChunks")
            self.assertEqual("override.tag", hide.kind)
            self.assertEqual(3, hide.line)
            self.assertEqual((1 << 64) - 1 - 5, hide.details["components"][0]["mask"])
            self.assertEqual([0, 2], hide.details["components"][0]["chunks"])
            raw = next(ref for ref in references if ref.identity == "RawMask")
            self.assertEqual(15, raw.details["components"][0]["mask"])
            coverage = build_archivexl_coverage(documents, references)
            operation = coverage["override_operations"][0]
            self.assertEqual(3, operation["definitions"])
            self.assertEqual(3, operation["components"])
            self.assertEqual(4, operation["chunk_references"])

    def test_override_tag_comparison_uses_whole_definition_last_wins(self) -> None:
        references = [
            Reference(
                "archivexl", "override.tag", "SameTag", mod, f"{mod}.xl",
                details={"fingerprint": "same"},
            )
            for mod in ("A", "B")
        ]
        references.extend(
            [
                Reference(
                    "archivexl", "override.tag", "DifferentTag", mod,
                    f"{mod}.xl", details={"fingerprint": fingerprint},
                )
                for mod, fingerprint in (("A", "first"), ("B", "second"))
            ]
        )
        findings = compare_override_references(references)
        self.assertEqual(
            {"AXL-OVERRIDE-TAG-CONFLICT", "AXL-OVERRIDE-TAG-DUPLICATE"},
            {finding.rule_id for finding in findings},
        )

    def test_override_shape_rejects_out_of_range_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad-overrides.xl"
            path.write_text(
                "overrides:\n  tags:\n    Bad:\n      body: {show: [64]}\n",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], references)
            self.assertEqual("AXL-OVERRIDE-SHAPE", findings[0].rule_id)
            self.assertEqual(4, findings[0].evidence[0]["line"])

    def test_extracts_journal_declaration_with_structural_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "journal.xl"
            path.write_text(
                "journal:\n  - mod\\example\\entries.journal\n",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], findings)
            self.assertEqual("journal", references[0].kind)
            self.assertEqual(2, references[0].line)

    def test_parses_effective_journal_paths_and_edit_markers(self) -> None:
        declaration = Reference(
            "archivexl", "journal", r"mod\example.journal", "A", "a.xl", 7
        )
        serialized = {
            "Data": {
                "RootChunk": {
                    "$type": "gameJournalResource",
                    "entry": {
                        "HandleId": "0",
                        "Data": {
                            "$type": "gameJournalRootFolderEntry",
                            "id": "",
                            "entries": [
                                {
                                    "Data": {
                                        "$type": "gameJournalFolderEntry",
                                        "id": "contacts",
                                        "entries": [
                                            {
                                                "Data": {
                                                    "$type": "gameJournalContact",
                                                    "id": "judy/thread*",
                                                    "name": "Example",
                                                }
                                            }
                                        ],
                                    }
                                }
                            ],
                        },
                    },
                }
            }
        }
        references, findings = parse_journal_payload(
            declaration, serialized, "a.archive"
        )
        self.assertEqual([], findings)
        self.assertEqual(2, len(references))
        self.assertEqual("contacts/judy/thread", references[1].identity)
        self.assertTrue(references[1].details["marked_for_edit"])
        self.assertEqual(7, references[1].line)

    def test_journal_comparison_distinguishes_containers_conflicts_and_edits(self) -> None:
        references = [
            Reference(
                "archivexl", "journal.entry", "contacts", mod, f"{mod}.xl",
                details={"is_container": True, "marked_for_edit": False,
                         "entry_type": "folder", "fingerprint": mod},
            )
            for mod in ("A", "B")
        ]
        references.extend(
            [
                Reference(
                    "archivexl", "journal.entry", "contacts/shared", mod,
                    f"{mod}.xl", details={
                        "is_container": False,
                        "marked_for_edit": False,
                        "entry_type": "message",
                        "fingerprint": mod,
                    },
                )
                for mod in ("A", "B")
            ]
        )
        references.extend(
            [
                Reference(
                    "archivexl", "journal.entry", "contacts/edit", mod,
                    f"{mod}.xl", details={
                        "is_container": False,
                        "marked_for_edit": mod == "A",
                        "entry_type": "message",
                        "fingerprint": mod,
                    },
                )
                for mod in ("A", "B")
            ]
        )
        findings, stats = compare_journal_entries(references)
        self.assertEqual(
            {
                "AXL-JOURNAL-CONTAINER-COMPOSABLE",
                "AXL-JOURNAL-EDIT-OVERLAP",
                "AXL-JOURNAL-ENTRY-CONFLICT",
            },
            {finding.rule_id for finding in findings},
        )
        self.assertEqual(1, stats["composable_entries"])
        self.assertEqual(1, stats["conflicting_entries"])
        self.assertEqual(1, stats["review_entries"])

    def test_extracts_quest_phase_parent_and_attachment_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "quest.xl"
            path.write_text(
                """quest:
  phases:
    - path: mod\\example\\child.questphase
      parent: base\\quest\\cyberpunk2077.quest
      input:
        node: [4]
        socket: Out1
""",
                encoding="utf-8",
            )
            documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], findings)
            self.assertEqual({"quest.phase", "quest.parent"}, {r.kind for r in references})
            phase = next(r for r in references if r.kind == "quest.phase")
            parent = next(r for r in references if r.kind == "quest.parent")
            self.assertEqual(3, phase.line)
            self.assertEqual(4, parent.line)
            self.assertEqual("input", phase.details["attachment_kind"])
            self.assertEqual({"node": [4], "socket": "Out1"}, phase.details["attachment"])
            coverage = build_archivexl_coverage(documents, references)
            self.assertEqual(1, coverage["quest_operations"][0]["declarations"])

    def test_duplicate_quest_merge_is_reported_without_flagging_shared_parent(self) -> None:
        duplicate = [
            Reference(
                "archivexl", "quest.phase", r"mod\shared.questphase", mod,
                f"{mod}.xl", details={
                    "parent": r"base\quest\cyberpunk2077.quest",
                    "attachment_kind": "connection",
                    "attachment_key": "[1,2,3]",
                },
            )
            for mod in ("A", "B")
        ]
        shared_parent_only = Reference(
            "archivexl", "quest.phase", r"mod\different.questphase", "C", "c.xl",
            details={
                "parent": r"base\quest\cyberpunk2077.quest",
                "attachment_kind": "root",
                "attachment_key": "null",
            },
        )
        findings = compare_quest_references([*duplicate, shared_parent_only])
        self.assertEqual(1, len(findings))
        self.assertEqual("AXL-QUEST-MERGE-DUPLICATE", findings[0].rule_id)

    def test_quest_resolution_distinguishes_owned_official_cross_mod_and_missing(self) -> None:
        references = [
            Reference("archivexl", "quest.phase", r"mod\owned.questphase", "A", "a.xl"),
            Reference("archivexl", "quest.parent", r"base\quest\cyberpunk2077.quest", "A", "a.xl"),
            Reference("archivexl", "quest.phase", r"mod\foreign.questphase", "A", "a.xl"),
            Reference("archivexl", "quest.parent", r"mod\foreign.quest", "A", "a.xl"),
            Reference("archivexl", "quest.phase", r"mod\missing.questphase", "A", "a.xl"),
            Reference("archivexl", "quest.parent", r"mod\missing.quest", "A", "a.xl"),
        ]
        manifests = [
            ArchiveManifest(
                "A", "a.archive", "a" * 64, 1, "test",
                [ArchiveMember(r"mod\owned.questphase")],
            ),
            ArchiveManifest(
                "B", "b.archive", "b" * 64, 1, "test",
                [
                    ArchiveMember(r"mod\foreign.questphase"),
                    ArchiveMember(r"mod\foreign.quest"),
                ],
            ),
        ]
        findings, stats = resolve_quest_references(references, manifests)
        self.assertEqual(
            {
                "AXL-QUEST-CROSS-MOD-PARENT",
                "AXL-QUEST-CROSS-MOD-PHASE",
                "AXL-QUEST-PARENT-NOT-FOUND",
                "AXL-QUEST-PHASE-NOT-FOUND",
            },
            {finding.rule_id for finding in findings},
        )
        self.assertEqual(1, stats["phase_own"])
        self.assertEqual(1, stats["phase_cross_mod"])
        self.assertEqual(1, stats["phase_missing"])
        self.assertEqual(1, stats["parent_official"])
        self.assertEqual(1, stats["parent_cross_mod"])
        self.assertEqual(1, stats["parent_missing"])
        self.assertEqual(2, stats["missing_targets"])

    def test_patch_payload_named_objects_have_stable_identities(self) -> None:
        declaration = Reference(
            "archivexl",
            "resource.patch",
            r"base\player.ent",
            "A",
            "a.xl",
            line=5,
            details={"source": r"mod\patch.ent"},
        )
        serialized = {
            "Data": {
                "RootChunk": {
                    "$type": "entEntityTemplate",
                    "components": [
                        {"$type": "entMeshComponent", "name": "Body:Example"}
                    ],
                }
            }
        }
        references, findings = parse_resource_patch_payload(
            declaration, serialized, "a.archive"
        )
        self.assertEqual([], findings)
        self.assertEqual(1, len(references))
        self.assertEqual(
            "components[name=Body:Example]",
            references[0].details["inner_identity"],
        )
        self.assertEqual(5, references[0].line)

    def test_patch_payload_same_inner_identity_with_different_data_conflicts(self) -> None:
        declarations = []
        entries = []
        for mod, path in (("A", r"a\mesh.mesh"), ("B", r"b\mesh.mesh")):
            declaration = Reference(
                "archivexl",
                "resource.patch",
                r"base\shared.mesh",
                mod,
                f"{mod}.xl",
                details={"source": path},
            )
            declarations.append(declaration)
            parsed, _findings = parse_resource_patch_payload(
                declaration,
                {
                    "Data": {
                        "RootChunk": {
                            "$type": "CMesh",
                            "appearances": [
                                {"name": "shared", "value": mod}
                            ],
                        }
                    }
                },
                f"{mod}.archive",
            )
            entries.extend(parsed)
        finding = compare_patch_target_entries(declarations, entries, True)
        self.assertEqual("AXL-RESOURCE-PATCH-INNER-CONFLICT", finding.rule_id)
        self.assertEqual("conflict", finding.severity)

    def test_patch_payload_disjoint_inner_identities_are_composable(self) -> None:
        declarations = []
        entries = []
        for mod in ("A", "B"):
            declaration = Reference(
                "archivexl",
                "resource.patch",
                r"base\shared.ent",
                mod,
                f"{mod}.xl",
                details={"source": f"{mod}.ent"},
            )
            declarations.append(declaration)
            parsed, _findings = parse_resource_patch_payload(
                declaration,
                {
                    "Data": {
                        "RootChunk": {
                            "$type": "entEntityTemplate",
                            "components": [{"name": f"component-{mod}"}],
                        }
                    }
                },
                f"{mod}.archive",
            )
            entries.extend(parsed)
        finding = compare_patch_target_entries(declarations, entries, True)
        self.assertEqual("AXL-RESOURCE-PATCH-DISJOINT", finding.rule_id)

    def test_parses_serialized_factory_rows(self) -> None:
        declaration = Reference(
            "archivexl",
            "factory",
            r"mod\factory.csv",
            "Example",
            "example.xl",
            line=2,
        )
        serialized = {
            "Data": {
                "RootChunk": {
                    "$type": "C2dArray",
                    "compiledHeaders": ["name", "path", "preload"],
                    "compiledData": [
                        ["example_entity", r"mod\example.ent", "true"]
                    ],
                }
            }
        }
        references, findings = parse_factory_payload(
            declaration, serialized, "example.archive"
        )
        self.assertEqual([], findings)
        self.assertEqual(1, len(references))
        self.assertEqual("example_entity", references[0].identity)
        self.assertEqual(r"mod\example.ent", references[0].details["target_path"])
        self.assertEqual(0, references[0].details["row_index"])
        self.assertEqual(2, references[0].line)

    def test_competing_factory_name_is_a_conflict(self) -> None:
        references = [
            Reference(
                "archivexl",
                "factory.entry",
                "shared_entity",
                "A",
                "a.xl",
                details={"target_path": r"a\root.ent"},
            ),
            Reference(
                "archivexl",
                "factory.entry",
                "shared_entity",
                "B",
                "b.xl",
                details={"target_path": r"b\root.ent"},
            ),
        ]
        findings = compare_factory_entries(references)
        self.assertEqual(1, len(findings))
        self.assertEqual("AXL-FACTORY-NAME-CONFLICT", findings[0].rule_id)

    def test_factory_target_validation_distinguishes_provider_states(self) -> None:
        references = [
            Reference(
                "archivexl",
                "factory.entry",
                "owned",
                "A",
                "a.xl",
                details={"target_path": r"a\owned.ent"},
            ),
            Reference(
                "archivexl",
                "factory.entry",
                "foreign",
                "A",
                "a.xl",
                details={"target_path": r"b\foreign.ent"},
            ),
            Reference(
                "archivexl",
                "factory.entry",
                "missing",
                "A",
                "a.xl",
                details={"target_path": r"missing.ent"},
            ),
        ]
        manifests = [
            ArchiveManifest(
                "A", "a.archive", "a" * 64, 1, "test", [ArchiveMember(r"a\owned.ent")]
            ),
            ArchiveManifest(
                "B", "b.archive", "b" * 64, 1, "test", [ArchiveMember(r"b\foreign.ent")]
            ),
        ]
        findings, stats = validate_factory_targets(references, manifests)
        self.assertEqual(1, stats["verified_targets"])
        self.assertEqual(1, stats["cross_mod_targets"])
        self.assertEqual(1, stats["missing_targets"])
        self.assertEqual(
            {"AXL-FACTORY-CROSS-MOD-TARGET", "AXL-FACTORY-TARGET-NOT-FOUND"},
            {item.rule_id for item in findings},
        )

    def test_parses_serialized_localization_entries(self) -> None:
        declaration = Reference(
            "archivexl",
            "localization.onscreens",
            r"mod\localization.json",
            "Example",
            "example.xl",
            line=4,
            details={"locale": "en-us"},
        )
        serialized = {
            "Data": {
                "RootChunk": {
                    "root": {
                        "Data": {
                            "entries": [
                                {
                                    "secondaryKey": "Example-Key",
                                    "primaryKey": "42",
                                    "femaleVariant": "Example text",
                                    "maleVariant": "",
                                }
                            ]
                        }
                    }
                }
            }
        }
        references = parse_localization_payload(
            declaration, serialized, "example.archive"
        )
        self.assertEqual(2, len(references))
        self.assertEqual(
            {"localization.entry.primary", "localization.entry.secondary"},
            {item.kind for item in references},
        )
        self.assertEqual(4, references[0].details["declaration_line"])
        self.assertEqual(4, references[0].line)
        self.assertEqual(0, references[0].details["entry_index"])

    def test_competing_localization_secondary_key_is_a_conflict(self) -> None:
        references = [
            Reference(
                "archivexl",
                "localization.entry.secondary",
                "en-us#Shared-Key",
                "A",
                "a.archive::a.json",
                details={
                    "secondary_key": "Shared-Key",
                    "female_variant": "Text A",
                    "male_variant": "",
                },
            ),
            Reference(
                "archivexl",
                "localization.entry.secondary",
                "en-us#Shared-Key",
                "B",
                "b.archive::b.json",
                details={
                    "secondary_key": "Shared-Key",
                    "female_variant": "Text B",
                    "male_variant": "",
                },
            ),
        ]
        findings = compare_localization_entries(references)
        self.assertEqual(1, len(findings))
        self.assertEqual("AXL-LOC-SECONDARY-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_extracts_all_observed_resource_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "resources.xl"
            path.write_text(
                """resource:
  patch:
    mod\\patch.mesh:
      props: [appearances]
      targets:
        - !include player.ent
  copy:
    base\\original.mesh: [mod\\copied.mesh]
  link:
    mod\\source.mesh: [mod\\alias.mesh]
  scope:
    player.ent: [base\\player.ent]
  fix:
    base\\target.mesh:
      paths:
        base\\old.mesh: mod\\new.mesh
""",
                encoding="utf-8",
            )
            documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual(
                {
                    "resource.copy",
                    "resource.fix",
                    "resource.link",
                    "resource.patch",
                    "resource.scope",
                },
                {reference.kind for reference in references},
            )
            patch = next(
                reference
                for reference in references
                if reference.kind == "resource.patch"
            )
            self.assertEqual("include", patch.details["target_tag"])
            self.assertEqual(["appearances"], patch.details["properties"])
            self.assertEqual(6, patch.line)
            coverage = build_archivexl_coverage(documents, references)
            self.assertEqual(5, len(coverage["resource_operations"]))
            self.assertTrue(
                all(
                    operation["status"] == "analyzed"
                    for operation in coverage["resource_operations"]
                )
            )
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_competing_resource_redirect_targets_are_a_conflict(self) -> None:
        references = [
            Reference(
                "archivexl",
                "resource.copy",
                "mod\\target.mesh",
                "A",
                "a.xl",
                details={"source": "base\\a.mesh"},
            ),
            Reference(
                "archivexl",
                "resource.link",
                "mod\\target.mesh",
                "B",
                "b.xl",
                details={"source": "base\\b.mesh"},
            ),
        ]
        findings = compare_resource_references(references)
        self.assertEqual("AXL-RESOURCE-TARGET-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_resource_patches_on_same_target_are_composable(self) -> None:
        references = [
            Reference(
                "archivexl",
                "resource.patch",
                "base\\target.mesh",
                "A",
                "a.xl",
                details={"source": "mod\\a.mesh"},
            ),
            Reference(
                "archivexl",
                "resource.patch",
                "base\\target.mesh",
                "B",
                "b.xl",
                details={"source": "mod\\b.mesh"},
            ),
        ]
        findings = compare_resource_references(references)
        self.assertEqual("AXL-RESOURCE-PATCH-COMPOSABLE", findings[0].rule_id)
        self.assertEqual("info", findings[0].severity)

    def test_contradictory_resource_fixes_are_a_conflict(self) -> None:
        references = [
            Reference(
                "archivexl",
                "resource.fix",
                "base\\target.mesh#paths#old",
                "A",
                "a.xl",
                details={"replacement": "mod\\a.mesh"},
            ),
            Reference(
                "archivexl",
                "resource.fix",
                "base\\target.mesh#paths#old",
                "B",
                "b.xl",
                details={"replacement": "mod\\b.mesh"},
            ),
        ]
        findings = compare_resource_references(references)
        self.assertEqual("AXL-RESOURCE-FIX-CONFLICT", findings[0].rule_id)

    def test_parses_json_and_extracts_localization_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text(
                '{"localization":{"onscreens":{"en-us":"mod\\\\loc\\\\en-us.json"}}}',
                encoding="utf-8",
            )
            documents, references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual(1, len(documents))
            self.assertEqual("localization.onscreens", references[0].kind)
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_duplicate_yaml_key_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text("streaming:\n  blocks: [a]\n  blocks: [b]\n", encoding="utf-8")
            _documents, _references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual("AXL-PARSE", findings[0].rule_id)

    def test_json_with_tab_indentation_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text('{\n\t"streaming": {"blocks": ["mod/all.streamingblock"]}\n}', encoding="utf-8")
            documents, references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual(1, len(documents))
            self.assertEqual("streaming.block", references[0].kind)
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_yaml_trailing_tab_uses_lenient_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text("streaming:\n  blocks:\n  - mod/all.streamingblock\t\n", encoding="utf-8")
            documents, _references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual(1, len(documents))
            self.assertIn("AXL-NONSTANDARD-TABS", [item.rule_id for item in findings])

    def test_conflicting_expected_nodes(self) -> None:
        refs = [
            Reference("archivexl", "streaming.sector", "base\\sector", "A", "a.xl", details={"expected_nodes": 10}),
            Reference("archivexl", "streaming.sector", "base\\sector", "B", "b.xl", details={"expected_nodes": 11}),
        ]
        findings = compare_references(refs)
        self.assertEqual("AXL-SECTOR-EXPECTED-NODES", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_sector_and_node_deletion_use_structural_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "deletions.xl"
            path.write_text(
                """streaming:
  sectors:
    - path: base\\worlds\\example.streamingsector
      nodeDeletions:
        - index: 179
          type: worldEntityNode
""",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            lines = {item.kind: item.line for item in references}
            self.assertEqual(3, lines["streaming.sector"])
            self.assertEqual(5, lines["streaming.node_deletion"])
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_sector_reviews_are_aggregated_by_mod_set(self) -> None:
        refs = [
            Reference("archivexl", "streaming.sector", "sector_a", "A", "a.xl"),
            Reference("archivexl", "streaming.sector", "sector_a", "B", "b.xl"),
            Reference("archivexl", "streaming.sector", "sector_b", "A", "a.xl"),
            Reference("archivexl", "streaming.sector", "sector_b", "B", "b.xl"),
        ]
        findings = compare_references(refs)
        self.assertEqual(1, len(findings))
        self.assertEqual("2 overlapping streaming sectors", findings[0].summary)

    def test_archive_list_output(self) -> None:
        members = parse_archive_list_output("foo\\bar.json\nfoo\\mesh.mesh\n")
        self.assertEqual(["foo\\bar.json", "foo\\mesh.mesh"], [item.path for item in members])

    def test_loose_archive_mod_resource_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "en-us.json"
            path.write_text("{}", encoding="utf-8")
            loose = artifact(path, "Example")
            loose.relative_path = r"archive\pc\mod\example\localization\en-us.json"
            loose.extension = ".json"
            reference = Reference(
                "archivexl",
                "localization.onscreens",
                r"example\localization\en-us.json",
                "Example",
                "example.xl",
            )
            self.assertEqual([], resolve_archive_references([reference], [], [loose]))


if __name__ == "__main__":
    unittest.main()
