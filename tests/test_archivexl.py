from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.archives import parse_archive_list_output
from cp77compat.archivexl import (
    build_archivexl_coverage,
    compare_override_references,
    compare_player_references,
    compare_quest_references,
    compare_references,
    compare_resource_references,
    compare_streaming_mutations,
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


def artifact(
    path: Path,
    mod: str,
    deployed_state: str = "unknown",
    deployed_source: str | None = None,
) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=r"archive\pc\mod\test.archive.xl",
        extension=".xl",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state=deployed_state,
        deployed_source=deployed_source,
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

    def test_extracts_player_body_types_with_exact_names_and_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "player.xl"
            path.write_text(
                "player:\n  bodyTypes:\n    - ANGEL\n    - Angel\n",
                encoding="utf-8",
            )
            documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], findings)
            self.assertEqual(
                [("ANGEL", 3, "Body:ANGEL"), ("Angel", 4, "Body:Angel")],
                [
                    (reference.identity, reference.line, reference.details["body_tag"])
                    for reference in references
                ],
            )
            self.assertTrue(
                all(reference.kind == "player.body_type" for reference in references)
            )
            coverage = build_archivexl_coverage(documents, references)
            section = next(
                item for item in coverage["sections"] if item["name"] == "player"
            )
            self.assertEqual("analyzed", section["status"])
            operation = coverage["player_operations"][0]
            self.assertEqual(2, operation["registrations"])
            self.assertEqual(2, operation["unique_body_types"])

    def test_player_mixed_sequence_keeps_valid_scalars_and_reports_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad-player.xl"
            path.write_text(
                "player:\n  bodyTypes: [ANGEL, {bad: value}]\n",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual(["ANGEL"], [reference.identity for reference in references])
            self.assertEqual("AXL-PLAYER-SHAPE", findings[0].rule_id)
            self.assertEqual(2, findings[0].evidence[0]["line"])

    def test_player_accepts_single_scalar_body_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "scalar-player.xl"
            path.write_text("player:\n  bodyTypes: SOLO\n", encoding="utf-8")
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], findings)
            self.assertEqual([("SOLO", 2)], [
                (reference.identity, reference.line) for reference in references
            ])

    def test_player_duplicate_comparison_is_case_sensitive_and_idempotent(self) -> None:
        references = [
            Reference(
                "archivexl",
                "player.body_type",
                body_type,
                mod,
                f"{mod}.xl",
                details={"body_tag": f"Body:{body_type}"},
            )
            for mod, body_type in (("A", "ANGEL"), ("B", "ANGEL"), ("C", "Angel"))
        ]
        findings = compare_player_references(references)
        self.assertEqual(1, len(findings))
        self.assertEqual("AXL-PLAYER-BODY-TYPE-DUPLICATE", findings[0].rule_id)
        self.assertEqual("info", findings[0].severity)
        self.assertEqual(["A", "B"], findings[0].participants)
        self.assertEqual("ANGEL", findings[0].evidence[0]["identity"])

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

    def test_resolves_forward_and_repeated_journal_handle_references(self) -> None:
        declaration = Reference(
            "archivexl", "journal", r"mod\shared.journal", "A", "a.xl", 8
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
                                {"HandleRefId": "1"},
                                {
                                    "HandleId": "1",
                                    "Data": {
                                        "$type": "gameJournalFolderEntry",
                                        "id": "contacts",
                                        "entries": [],
                                    },
                                },
                                {"HandleRefId": "1"},
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
        self.assertEqual(3, len(references))
        self.assertEqual(["contacts"] * 3, [item.identity for item in references])
        self.assertEqual("1", references[0].details["handle_ref_id"])
        self.assertIsNone(references[1].details["handle_ref_id"])
        self.assertEqual("1", references[2].details["handle_ref_id"])

    def test_consolidates_missing_and_cyclic_journal_handle_issues(self) -> None:
        declaration = Reference(
            "archivexl", "journal", r"mod\broken.journal", "A", "a.xl", 9
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
                                {"HandleRefId": "99"},
                                {
                                    "HandleId": "1",
                                    "Data": {
                                        "$type": "gameJournalFolderEntry",
                                        "id": "loop",
                                        "entries": [{"HandleRefId": "1"}],
                                    },
                                },
                            ],
                        },
                    },
                }
            }
        }
        references, findings = parse_journal_payload(
            declaration, serialized, "a.archive"
        )
        self.assertEqual(1, len(references))
        self.assertEqual(1, len(findings))
        issues = findings[0].evidence[0]["issues"]
        self.assertEqual(2, len(issues))
        self.assertIn("no matching HandleId", issues[0]["explanation"])
        self.assertIn("ancestor cycle", issues[1]["explanation"])

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
            Reference(
                "archivexl",
                "resource.scope",
                "cyberpunk2077.quest#cyberpunk2077_main.quest",
                "ArchiveXL",
                r"C:\Game\red4ext\plugins\ArchiveXL\Bundle\QuestBaseScope.xl",
                details={
                    "scope": "cyberpunk2077.quest",
                    "member": "cyberpunk2077_main.quest",
                },
            ),
            Reference("archivexl", "quest.phase", r"mod\owned.questphase", "A", "a.xl"),
            Reference("archivexl", "quest.parent", r"base\quest\cyberpunk2077.quest", "A", "a.xl"),
            Reference("archivexl", "quest.parent", "cyberpunk2077.quest", "A", "a.xl"),
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
        self.assertEqual(2, stats["parent_official"])
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

    def test_repeated_full_node_deletions_are_idempotent(self) -> None:
        refs = [
            Reference(
                "archivexl",
                "streaming.node_deletion",
                r"base\sector#7",
                mod,
                f"{mod}.xl",
                details={
                    "node_type": "worldStaticMeshNode",
                    "deletion_scope": "full",
                    "expected_elements": [],
                    "element_deletions": [],
                },
            )
            for mod in ("A", "B")
        ]
        findings = compare_references(refs)
        self.assertEqual(1, len(findings))
        self.assertEqual("AXL-NODE-DELETION-IDEMPOTENT", findings[0].rule_id)
        self.assertEqual("info", findings[0].severity)
        self.assertEqual("high", findings[0].confidence)

    def test_partial_node_deletions_are_composable_but_counts_must_match(self) -> None:
        refs = [
            Reference(
                "archivexl",
                "streaming.node_deletion",
                r"base\sector#7",
                mod,
                f"{mod}.xl",
                details={
                    "node_type": "worldInstancedMeshNode",
                    "deletion_scope": "partial",
                    "expected_elements": [count],
                    "element_deletions": [
                        {"element_index": element, "sub_element_index": -1}
                    ],
                },
            )
            for mod, count, element in (("A", 4, 0), ("B", 4, 1))
        ]
        findings = compare_references(refs)
        self.assertEqual("AXL-NODE-DELETION-COMPOSABLE", findings[0].rule_id)
        self.assertEqual("info", findings[0].severity)

        refs[1].details["expected_elements"] = [5]
        findings = compare_references(refs)
        self.assertEqual("AXL-NODE-DELETION-COUNT-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_node_deletion_type_disagreement_is_a_conflict(self) -> None:
        refs = [
            Reference(
                "archivexl",
                "streaming.node_deletion",
                r"base\sector#7",
                mod,
                f"{mod}.xl",
                details={
                    "node_type": node_type,
                    "deletion_scope": "full",
                    "expected_elements": [],
                    "element_deletions": [],
                },
            )
            for mod, node_type in (
                ("A", "worldStaticMeshNode"),
                ("B", "worldEntityNode"),
            )
        ]
        findings = compare_references(refs)
        self.assertEqual("AXL-NODE-DELETION-TYPE-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_repeated_collision_shape_deletions_are_a_conflict(self) -> None:
        refs = [
            Reference(
                "archivexl",
                "streaming.node_deletion",
                r"base\sector#7",
                mod,
                f"{mod}.xl",
                details={
                    "node_type": "worldCollisionNode",
                    "deletion_scope": "partial",
                    "effective_deletion_scope": "partial",
                    "expected_elements": [4],
                    "element_deletions": [
                        {"element_index": actor, "sub_element_index": shape}
                    ],
                },
            )
            for mod, actor, shape in (("A", 1, 0), ("B", 2, 1))
        ]
        findings = compare_references(refs)
        self.assertEqual(
            "AXL-NODE-DELETION-COLLISION-SHAPE-CONFLICT",
            findings[0].rule_id,
        )
        self.assertEqual("conflict", findings[0].severity)

    def test_sector_and_node_deletion_use_structural_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "deletions.xl"
            path.write_text(
                r"""streaming:
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
            deletion = next(
                item for item in references if item.kind == "streaming.node_deletion"
            )
            self.assertEqual("full", deletion.details["deletion_scope"])
            self.assertEqual([], deletion.details["element_deletions"])
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_out_of_range_node_deletion_is_skipped_before_sector_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            valid_path = root / "valid.xl"
            invalid_path = root / "invalid.xl"
            valid_path.write_text(
                r"""streaming:
  sectors:
    - path: base\worlds\example.streamingsector
      expectedNodes: 10
      nodeDeletions:
        - index: 7
          type: worldStaticMeshNode
""",
                encoding="utf-8",
            )
            invalid_path.write_text(
                r"""streaming:
  sectors:
    - path: base\worlds\example.streamingsector
      expectedNodes: 8
      nodeDeletions:
        - index: 8
          type: worldStaticMeshNode
""",
                encoding="utf-8",
            )

            _documents, references, findings = parse_documents(
                [artifact(valid_path, "Valid"), artifact(invalid_path, "Invalid")]
            )

            self.assertEqual(
                ["Valid"],
                [
                    reference.mod_name
                    for reference in references
                    if reference.kind == "streaming.sector"
                ],
            )
            invalid = next(
                item
                for item in findings
                if item.rule_id == "AXL-NODE-DELETION-SHAPE"
            )
            self.assertEqual("error", invalid.severity)
            self.assertEqual(8, invalid.evidence[0]["index"])
            self.assertEqual(8, invalid.evidence[0]["expected_nodes"])
            self.assertFalse(
                [
                    item
                    for item in compare_references(references)
                    if item.rule_id == "AXL-SECTOR-EXPECTED-NODES"
                ]
            )

    def test_small_exact_path_override_replaces_original_and_inherits_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_path = root / "original" / "INCF.xl"
            winner_path = root / "fix" / "INCF.xl"
            original_path.parent.mkdir()
            winner_path.parent.mkdir()
            original_path.write_text(
                r"""localization:
  onscreens: incf\localization.json
streaming:
  sectors:
    - path: base\worlds\example.streamingsector
      expectedNodes: 10
      nodeDeletions:
        - index: 10
          type: worldStaticMeshNode
""",
                encoding="utf-8",
            )
            winner_path.write_text(
                r"""localization:
  onscreens: incf\localization.json
streaming:
  sectors:
    - path: base\worlds\example.streamingsector
      expectedNodes: 10
      nodeDeletions:
        - index: 7
          type: worldStaticMeshNode
""",
                encoding="utf-8",
            )

            documents, references, findings = parse_documents(
                [
                    artifact(
                        original_path,
                        "INCF Original",
                        "overridden",
                        "INCF Fix",
                    ),
                    artifact(winner_path, "INCF Fix", "deployed", "INCF Fix"),
                ]
            )

            self.assertEqual(1, len(documents))
            self.assertEqual(winner_path, documents[0].artifact.absolute_path)
            self.assertEqual("INCF Original", documents[0].mod_name)
            self.assertTrue(references)
            self.assertEqual({"INCF Original"}, {item.mod_name for item in references})
            self.assertEqual(
                {str(winner_path)}, {item.source_path for item in references}
            )
            self.assertTrue(
                all(
                    item.details.get("deployed_mod_name") == "INCF Fix"
                    and item.details.get("override_origin") == "INCF Original"
                    for item in references
                )
            )
            self.assertFalse(
                [item for item in findings if item.rule_id == "AXL-NODE-DELETION-SHAPE"]
            )
            self.assertFalse(compare_references(references))

    def test_large_deletion_only_override_inherits_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_path = root / "original" / "quests.xl"
            winner_path = root / "fix" / "quests.xl"
            original_path.parent.mkdir()
            winner_path.parent.mkdir()
            retained = [
                "quest:",
                "  phases:",
                r"    - path: mod\retained.questphase",
                r"      parent: base\quest\cyberpunk2077.quest",
            ]
            optional = [
                line
                for index in range(30)
                for line in (
                    rf"    - path: mod\optional_{index}.questphase",
                    r"      parent: mod\quest\newgameplus.quest",
                )
            ]
            original_path.write_text(
                "\n".join([*retained, *optional, ""]), encoding="utf-8"
            )
            winner_path.write_text("\n".join([*retained, ""]), encoding="utf-8")

            documents, references, findings = parse_documents(
                [
                    artifact(
                        original_path,
                        "Quest Original",
                        "overridden",
                        "Quest Cleanup",
                    ),
                    artifact(
                        winner_path,
                        "Quest Cleanup",
                        "deployed",
                        "Quest Cleanup",
                    ),
                ]
            )

            self.assertEqual(1, len(documents))
            self.assertEqual("Quest Original", documents[0].mod_name)
            self.assertEqual(
                {"Quest Original"}, {reference.mod_name for reference in references}
            )
            self.assertTrue(
                all(
                    reference.details.get("deployed_mod_name") == "Quest Cleanup"
                    and reference.details.get("override_origin") == "Quest Original"
                    for reference in references
                )
            )
            self.assertFalse(findings)

    def test_partial_node_deletion_preserves_actor_and_shape_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "partial-deletions.xl"
            path.write_text(
                r"""streaming:
  sectors:
    - path: base\worlds\example.streamingsector
      expectedNodes: 10
      nodeDeletions:
        - index: 7
          type: worldCollisionNode
          expectedActors: 4
          actorDeletions: [1, [2, 3]]
""",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            deletion = next(
                item for item in references if item.kind == "streaming.node_deletion"
            )
            self.assertEqual("partial", deletion.details["deletion_scope"])
            self.assertEqual("partial", deletion.details["effective_deletion_scope"])
            self.assertEqual([4], deletion.details["expected_elements"])
            self.assertEqual(
                [
                    {"element_index": 1, "sub_element_index": -1},
                    {"element_index": 2, "sub_element_index": 3},
                ],
                deletion.details["element_deletions"],
            )
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_node_disjoint_sectors_are_aggregated_by_mod_set(self) -> None:
        refs = [
            Reference("archivexl", "streaming.sector", "sector_a", "A", "a.xl"),
            Reference("archivexl", "streaming.sector", "sector_a", "B", "b.xl"),
            Reference("archivexl", "streaming.sector", "sector_b", "A", "a.xl"),
            Reference("archivexl", "streaming.sector", "sector_b", "B", "b.xl"),
        ]
        findings = compare_references(refs)
        self.assertEqual(1, len(findings))
        self.assertEqual("AXL-SECTOR-NODE-DISJOINT", findings[0].rule_id)
        self.assertEqual("info", findings[0].severity)
        self.assertEqual("2 node-disjoint shared streaming sectors", findings[0].summary)

    def test_extracts_effective_node_and_element_mutation_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mutations.xl"
            path.write_text(
                r"""streaming:
  sectors:
    - path: base\worlds\example.streamingsector
      expectedNodes: 10
      nodeMutations:
        - index: 7
          type: worldInstancedMeshNode
          position: [1, 2, 3, 99]
          resource: first.mesh
          mesh: final.mesh
          appearance: first
          meshAppearance: final
          expectedInstances: 3
          instanceMutations:
            - index: 1
              position: [4, 5, 6, 77]
              scale: [2, 2, 2]
""",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual([], findings)
            node = next(
                item for item in references if item.kind == "streaming.node_mutation"
            )
            element = next(
                item
                for item in references
                if item.kind == "streaming.node_element_mutation"
            )
            self.assertEqual(6, node.line)
            self.assertEqual([1.0, 2.0, 3.0, 0.0], node.details["writes"]["position"])
            self.assertEqual("final.mesh", node.details["writes"]["resource"])
            self.assertEqual("final", node.details["writes"]["appearance"])
            self.assertEqual(15, element.line)
            self.assertEqual(3, element.details["expected_elements"])
            self.assertEqual(
                {"position": [4.0, 5.0, 6.0, 0.0], "scale": [2.0, 2.0, 2.0]},
                element.details["writes"],
            )

    def test_node_mutations_distinguish_disjoint_idempotent_and_conflicting_writes(self) -> None:
        def mutation(mod: str, writes: dict[str, object]) -> Reference:
            return Reference(
                "archivexl", "streaming.node_mutation", r"base\sector#7",
                mod, f"{mod}.xl", details={
                    "sector": r"base\sector",
                    "index": 7,
                    "node_type": "worldEntityNode",
                    "writes": writes,
                    "element_mutations": [],
                },
            )

        findings = compare_streaming_mutations(
            [mutation("A", {"position": [1, 2, 3, 0]}), mutation("B", {"appearance": "x"})]
        )
        self.assertEqual("AXL-NODE-MUTATION-COMPOSABLE", findings[0].rule_id)

        findings = compare_streaming_mutations(
            [mutation("A", {"appearance": "x"}), mutation("B", {"appearance": "x"})]
        )
        self.assertEqual("AXL-NODE-MUTATION-IDEMPOTENT", findings[0].rule_id)

        findings = compare_streaming_mutations(
            [mutation("A", {"appearance": "x"}), mutation("B", {"appearance": "y"})]
        )
        self.assertEqual("AXL-NODE-MUTATION-WRITE-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_destructible_instance_mutations_reset_unspecified_transform_fields(self) -> None:
        references = [
            Reference(
                "archivexl", "streaming.node_mutation", r"base\sector#7",
                mod, f"{mod}.xl", details={
                    "sector": r"base\sector",
                    "index": 7,
                    "node_type": "worldInstancedDestructibleMeshNode",
                    "writes": {},
                    "expected_elements": 4,
                    "element_mutations": [
                        {"element_index": 1, "writes": {property_name: value}}
                    ],
                },
            )
            for mod, property_name, value in (
                ("A", "position", [1, 2, 3, 0]),
                ("B", "orientation", [0, 0, 0, 1]),
            )
        ]
        findings = compare_streaming_mutations(references)
        self.assertEqual(
            "AXL-NODE-MUTATION-DESTRUCTIBLE-CONFLICT", findings[0].rule_id
        )

    def test_full_deletion_dominates_entity_mutation_but_static_scale_is_ordered(self) -> None:
        def operations(node_type: str, writes: dict[str, object]) -> list[Reference]:
            return [
                Reference(
                    "archivexl", "streaming.node_mutation", r"base\sector#7",
                    "A", "a.xl", details={
                        "sector": r"base\sector", "index": 7,
                        "node_type": node_type, "writes": writes,
                        "element_mutations": [],
                    },
                ),
                Reference(
                    "archivexl", "streaming.node_deletion", r"base\sector#7",
                    "B", "b.xl", details={
                        "sector": r"base\sector", "index": 7,
                        "node_type": node_type, "deletion_scope": "full",
                        "element_deletions": [],
                    },
                ),
            ]

        findings = compare_streaming_mutations(
            operations("worldEntityNode", {"appearance": "default"})
        )
        self.assertEqual(
            "AXL-NODE-MUTATION-DELETION-REDUNDANT", findings[0].rule_id
        )
        findings = compare_streaming_mutations(
            operations("worldStaticMeshNode", {"scale": [1, 1, 1]})
        )
        self.assertEqual(
            "AXL-NODE-MUTATION-DELETION-CONFLICT", findings[0].rule_id
        )

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

    def test_exact_path_override_can_supply_companion_archive_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "original.archive.xl"
            path.write_text("localization: {}\n", encoding="utf-8")
            winner = artifact(path, "Compatibility Patch", deployed_state="deployed")
            reference = Reference(
                "archivexl",
                "localization.onscreens",
                r"localization\it-it\onscreens\example.json",
                "Original Mod",
                str(path),
                details={"override_origin": "Original Mod"},
            )
            patch_manifest = ArchiveManifest(
                mod_name="Compatibility Patch",
                archive_path=str(Path(temp) / "patch.archive"),
                sha256="0" * 64,
                size=1,
                wolvenkit_version="test",
                members=[
                    ArchiveMember(
                        r"localization\it-it\onscreens\example.json"
                    )
                ],
            )

            self.assertEqual(
                [],
                resolve_archive_references(
                    [reference], [patch_manifest], [winner]
                ),
            )
            findings = resolve_archive_references([reference], [patch_manifest])
            self.assertEqual("AXL-CROSS-MOD-RESOURCE", findings[0].rule_id)



if __name__ == "__main__":
    unittest.main()
