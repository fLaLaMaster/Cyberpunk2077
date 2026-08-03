from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import Artifact, Finding, Reference


CET_MODS_PREFIX = "bin\\x64\\plugins\\cyber_engine_tweaks\\mods\\"
KNOWN_EVENTS = {
    "onHook",
    "onTweak",
    "onInit",
    "onShutdown",
    "onUpdate",
    "onDraw",
    "onOverlayOpen",
    "onOverlayClose",
}
BINDING_CALLS = {"registerHotkey": "binding.hotkey", "registerInput": "binding.input"}
HOOK_CALLS = {
    "Observe": "hook.observe_before",
    "ObserveBefore": "hook.observe_before",
    "ObserveAfter": "hook.observe_after",
    "Override": "hook.override",
}
SETTINGS_CALLS = {
    "addTab",
    "addSubcategory",
    "addSwitch",
    "addSelectorString",
    "addRangeInt",
    "addRangeFloat",
    "addKeyBinding",
}
_BINDING_ID = re.compile(r"^[A-Za-z0-9_.]+$")


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    line: int
    start: int
    end: int


@dataclass(slots=True)
class CETDocument:
    artifact: Artifact
    mod_root: str
    relative_to_root: str
    token_count: int
    call_counts: dict[str, int]


def cet_artifact_location(artifact: Artifact) -> tuple[str, str] | None:
    normalized = artifact.relative_path.replace("/", "\\")
    if not normalized.casefold().startswith(CET_MODS_PREFIX.casefold()):
        return None
    remainder = normalized[len(CET_MODS_PREFIX):]
    root, separator, relative = remainder.partition("\\")
    if not separator or not root or not relative:
        return None
    return root, relative


def _long_bracket_end(source: str, index: int) -> tuple[int, int] | None:
    if index >= len(source) or source[index] != "[":
        return None
    cursor = index + 1
    while cursor < len(source) and source[cursor] == "=":
        cursor += 1
    if cursor >= len(source) or source[cursor] != "[":
        return None
    equals = cursor - index - 1
    closing = "]" + ("=" * equals) + "]"
    end = source.find(closing, cursor + 1)
    return (len(source), equals) if end < 0 else (end + len(closing), equals)


def _decode_short_string(raw: str) -> str:
    body = raw[1:-1]
    result: list[str] = []
    index = 0
    escapes = {
        "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r",
        "t": "\t", "v": "\v", "\\": "\\", "\"": "\"", "'": "'",
    }
    while index < len(body):
        char = body[index]
        if char != "\\" or index + 1 >= len(body):
            result.append(char)
            index += 1
            continue
        next_char = body[index + 1]
        if next_char == "z":
            index += 2
            while index < len(body) and body[index].isspace():
                index += 1
            continue
        result.append(escapes.get(next_char, next_char))
        index += 2
    return "".join(result)


def _lex(source: str) -> tuple[list[_Token], list[dict[str, Any]]]:
    tokens: list[_Token] = []
    issues: list[dict[str, Any]] = []
    index = 0
    line = 1
    while index < len(source):
        char = source[index]
        if char.isspace():
            line += char == "\n"
            index += 1
            continue
        if source.startswith("--", index):
            long_comment = _long_bracket_end(source, index + 2)
            if long_comment is not None:
                end, _ = long_comment
                if end == len(source) and not source.endswith("]"):
                    issues.append({"line": line, "reason": "unterminated long comment"})
                line += source[index:end].count("\n")
                index = end
                continue
            end = source.find("\n", index + 2)
            index = len(source) if end < 0 else end
            continue
        if char in {'"', "'"}:
            start = index
            start_line = line
            quote = char
            index += 1
            closed = False
            while index < len(source):
                if source[index] == "\\":
                    if index + 1 < len(source):
                        if source[index + 1] == "\n":
                            line += 1
                        index += 2
                    else:
                        index += 1
                    continue
                if source[index] == quote:
                    index += 1
                    closed = True
                    break
                line += source[index] == "\n"
                index += 1
            raw = source[start:index]
            if not closed:
                issues.append({"line": start_line, "reason": "unterminated short string"})
            tokens.append(_Token("string", _decode_short_string(raw) if closed else raw, start_line, start, index))
            continue
        long_string = _long_bracket_end(source, index)
        if long_string is not None:
            start = index
            start_line = line
            end, equals = long_string
            opening_length = equals + 2
            closing_length = equals + 2
            value = source[start + opening_length:end - closing_length]
            if value.startswith("\n"):
                value = value[1:]
            tokens.append(_Token("string", value, start_line, start, end))
            line += source[start:end].count("\n")
            index = end
            continue
        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < len(source) and (source[index].isalnum() or source[index] == "_"):
                index += 1
            tokens.append(_Token("name", source[start:index], line, start, index))
            continue
        if char.isdigit():
            start = index
            index += 1
            while index < len(source) and (source[index].isalnum() or source[index] in ".xXpP+-"):
                index += 1
            tokens.append(_Token("number", source[start:index], line, start, index))
            continue
        operator = next(
            (item for item in ("...", "::", "==", "~=", "<=", ">=", "//", "<<", ">>", "..")
             if source.startswith(item, index)),
            None,
        )
        if operator:
            tokens.append(_Token("symbol", operator, line, index, index + len(operator)))
            index += len(operator)
        else:
            tokens.append(_Token("symbol", char, line, index, index + 1))
            index += 1
    return tokens, issues


def _matching(tokens: list[_Token], start: int, opening: str, closing: str) -> int | None:
    depth = 0
    for index in range(start, len(tokens)):
        if tokens[index].value == opening:
            depth += 1
        elif tokens[index].value == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _argument_starts(tokens: list[_Token], open_index: int) -> tuple[list[int], int | None]:
    starts: list[int] = []
    if open_index + 1 >= len(tokens):
        return starts, None
    cursor = open_index + 1
    if tokens[cursor].value == ")":
        return starts, cursor
    starts.append(cursor)
    paren = 1
    bracket = 0
    brace = 0
    while cursor + 1 < len(tokens):
        cursor += 1
        value = tokens[cursor].value
        if value == "(":
            paren += 1
        elif value == ")":
            paren -= 1
            if paren == 0:
                return starts, cursor
        elif value == "[":
            bracket += 1
        elif value == "]" and bracket:
            bracket -= 1
        elif value == "{":
            brace += 1
        elif value == "}" and brace:
            brace -= 1
        elif value == "," and paren == 1 and bracket == 0 and brace == 0:
            starts.append(cursor + 1)
    return starts, None


def _literal_argument(tokens: list[_Token], starts: list[int], ordinal: int) -> str | None:
    if ordinal >= len(starts):
        return None
    token = tokens[starts[ordinal]]
    return token.value if token.kind == "string" else None


def _function_depths(tokens: list[_Token]) -> list[int]:
    depths: list[int] = []
    stack: list[str] = []
    pending_loop_do = 0
    for token in tokens:
        depths.append(sum(item == "function" for item in stack))
        value = token.value
        if value == "function":
            stack.append("function")
        elif value == "if":
            stack.append("if")
        elif value in {"for", "while"}:
            stack.append("loop")
            pending_loop_do += 1
        elif value == "do":
            if pending_loop_do:
                pending_loop_do -= 1
            else:
                stack.append("do")
        elif value == "repeat":
            stack.append("repeat")
        elif value == "until":
            if stack and stack[-1] == "repeat":
                stack.pop()
        elif value == "end" and stack:
            stack.pop()
    return depths


def _override_callback_details(
    tokens: list[_Token], starts: list[int], close_index: int | None
) -> dict[str, Any]:
    if len(starts) < 3 or close_index is None:
        return {"callback_inline": False, "calls_wrapped": None}
    start = starts[2]
    if tokens[start].value != "function" or start + 1 >= close_index or tokens[start + 1].value != "(":
        return {"callback_inline": False, "calls_wrapped": None}
    parameters_end = _matching(tokens, start + 1, "(", ")")
    if parameters_end is None or parameters_end >= close_index:
        return {"callback_inline": True, "calls_wrapped": None}
    parameters = [
        token.value
        for token in tokens[start + 2:parameters_end]
        if token.kind == "name"
    ]
    wrapped = parameters[-1] if parameters else None
    calls_wrapped = None
    if wrapped:
        calls_wrapped = any(
            tokens[index].value == wrapped and tokens[index + 1].value == "("
            for index in range(parameters_end + 1, close_index - 1)
        )
    body_fingerprint = hashlib.sha256(
        "\x1f".join(token.value for token in tokens[parameters_end + 1:close_index]).encode("utf-8")
    ).hexdigest()
    return {
        "callback_inline": True,
        "callback_parameter": wrapped,
        "calls_wrapped": calls_wrapped,
        "body_fingerprint": body_fingerprint,
    }


def _base_details(
    artifact: Artifact,
    root: str,
    relative: str,
    top_level: bool,
) -> dict[str, Any]:
    return {
        "mod_root": root,
        "relative_to_root": relative,
        "relative_path": artifact.relative_path,
        "deployed_state": artifact.deployed_state,
        "top_level": top_level,
        "reachable": False,
    }


def _parse_document(
    artifact: Artifact, root: str, relative: str, tokens: list[_Token]
) -> tuple[list[Reference], Counter[str]]:
    references: list[Reference] = []
    counts: Counter[str] = Counter()
    depths = _function_depths(tokens)
    if relative.casefold() == "init.lua":
        references.append(
            Reference(
                ecosystem="cet",
                kind="mod.entry",
                identity=root,
                mod_name=artifact.mod_name,
                source_path=str(artifact.absolute_path),
                line=1,
                details=_base_details(artifact, root, relative, True),
            )
        )
        counts["mod.entry"] += 1

    for index, token in enumerate(tokens[:-1]):
        if token.kind != "name" or tokens[index + 1].value != "(":
            continue
        call = token.value
        supported = (
            call == "registerForEvent"
            or call in BINDING_CALLS
            or call in HOOK_CALLS
            or call in {"require", "GetMod"}
            or call in SETTINGS_CALLS
        )
        if not supported:
            continue
        starts, close_index = _argument_starts(tokens, index + 1)
        first = _literal_argument(tokens, starts, 0)
        second = _literal_argument(tokens, starts, 1)
        top_level = depths[index] == 0
        details = _base_details(artifact, root, relative, top_level)
        details["call"] = call
        details["literal_arguments"] = sum(value is not None for value in (first, second))

        if call == "registerForEvent":
            kind = "event.registration" if first is not None else "event.dynamic"
            identity = f"{root}:{first}" if first is not None else f"{root}:<dynamic>@{token.line}"
            details["event"] = first
        elif call in BINDING_CALLS:
            kind = BINDING_CALLS[call] if first is not None else "binding.dynamic"
            identity = f"{root}:{first}" if first is not None else f"{root}:<dynamic>@{token.line}"
            details.update({"binding_id": first, "display_name": second})
        elif call in HOOK_CALLS:
            kind = HOOK_CALLS[call] if first is not None and second is not None else "hook.dynamic"
            identity = f"{first}.{second}" if first is not None and second is not None else f"<dynamic>@{root}:{token.line}"
            details.update({"class": first, "method": second})
            if call == "Override":
                details.update(_override_callback_details(tokens, starts, close_index))
        elif call == "require":
            kind = "module.require" if first is not None else "module.dynamic"
            identity = f"{root}:{first}" if first is not None else f"{root}:<dynamic>@{token.line}"
            details["module"] = first
        elif call == "GetMod":
            kind = "mod.dependency" if first is not None else "mod.dependency_dynamic"
            identity = first if first is not None else f"<dynamic>@{root}:{token.line}"
            details["target_mod_root"] = first
        else:
            if index == 0 or tokens[index - 1].value not in {".", ":"}:
                continue
            kind = f"settings.{call}" if first is not None else "settings.dynamic"
            identity = first if first is not None else f"<dynamic>@{root}:{token.line}"
            details.update({"settings_operation": call, "settings_path": first})

        references.append(
            Reference(
                ecosystem="cet",
                kind=kind,
                identity=identity,
                mod_name=artifact.mod_name,
                source_path=str(artifact.absolute_path),
                line=token.line,
                details=details,
            )
        )
        counts[kind] += 1
    return references, counts


def parse_cet_documents(
    artifacts: Iterable[Artifact],
) -> tuple[list[CETDocument], list[Reference], list[Finding]]:
    documents: list[CETDocument] = []
    references: list[Reference] = []
    findings: list[Finding] = []
    for artifact in artifacts:
        if artifact.extension.casefold() != ".lua":
            continue
        location = cet_artifact_location(artifact)
        if location is None:
            continue
        root, relative = location
        try:
            source = artifact.absolute_path.read_text(encoding="utf-8-sig", errors="strict")
        except (OSError, UnicodeError) as exc:
            findings.append(
                Finding(
                    rule_id="CET-LUA-READ-ERROR",
                    severity="error",
                    confidence="high",
                    summary=f"CET Lua file could not be read: {artifact.relative_path}",
                    explanation=str(exc),
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
            continue
        tokens, issues = _lex(source)
        document_references, counts = _parse_document(artifact, root, relative, tokens)
        references.extend(document_references)
        documents.append(CETDocument(artifact, root, relative, len(tokens), dict(counts)))
        if issues:
            findings.append(
                Finding(
                    rule_id="CET-LUA-LEX-ERROR",
                    severity="error",
                    confidence="high",
                    summary=f"CET Lua lexical structure is incomplete: {artifact.relative_path}",
                    explanation="Unterminated Lua strings or comments make later static references unreliable.",
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path), **issue} for issue in issues],
                )
            )
    return documents, references, findings


def _path_key(value: str) -> str:
    return value.replace("/", "\\").lstrip(".\\").casefold()


def _module_candidates(module: str) -> list[str]:
    normalized = module.replace("/", "\\").lstrip(".\\")
    candidates = [normalized]
    if not normalized.casefold().endswith(".lua"):
        candidates.extend([normalized + ".lua", normalized + "\\init.lua"])
    return [_path_key(candidate) for candidate in candidates]


def _active(reference: Reference) -> bool:
    return reference.details.get("deployed_state") != "overridden"


def _mark_reachable_and_resolve_modules(
    documents: list[CETDocument], references: list[Reference]
) -> dict[tuple[str, str], CETDocument]:
    documents_by_source = {
        str(document.artifact.absolute_path.resolve(strict=False)).casefold(): document
        for document in documents
    }
    modules: dict[tuple[str, str], CETDocument] = {}
    entries: list[CETDocument] = []
    for document in documents:
        if document.artifact.deployed_state == "overridden":
            continue
        key = (document.mod_root.casefold(), _path_key(document.relative_to_root))
        modules[key] = document
        if document.relative_to_root.casefold() == "init.lua":
            entries.append(document)

    requires_by_source: dict[str, list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind == "module.require" and _active(reference):
            requires_by_source[str(Path(reference.source_path).resolve(strict=False)).casefold()].append(reference)

    reachable_sources: set[str] = set()
    queue = deque(entries)
    while queue:
        document = queue.popleft()
        source_key = str(document.artifact.absolute_path.resolve(strict=False)).casefold()
        if source_key in reachable_sources:
            continue
        reachable_sources.add(source_key)
        for reference in requires_by_source.get(source_key, []):
            module = reference.details.get("module")
            provider = next(
                (modules.get((document.mod_root.casefold(), candidate)) for candidate in _module_candidates(module or "")
                 if modules.get((document.mod_root.casefold(), candidate)) is not None),
                None,
            )
            if provider is not None:
                reference.details.update({
                    "resolved": True,
                    "provider_path": str(provider.artifact.absolute_path),
                    "provider_mod_name": provider.artifact.mod_name,
                    "provider_relative_to_root": provider.relative_to_root,
                })
                if reference.details.get("top_level"):
                    queue.append(provider)
            else:
                reference.details["resolved"] = False

    for reference in references:
        source_key = str(Path(reference.source_path).resolve(strict=False)).casefold()
        reference.details["reachable"] = source_key in reachable_sources
    return modules


def _aggregate(
    groups: Iterable[tuple[str, list[Reference]]],
    rule_id: str,
    severity: str,
    confidence: str,
    label: str,
    explanation: str,
) -> list[Finding]:
    aggregated: dict[tuple[str, ...], list[tuple[str, list[Reference]]]] = defaultdict(list)
    for identity, group in groups:
        participants = tuple(sorted({item.mod_name for item in group}, key=str.casefold))
        aggregated[participants].append((identity, group))
    return [
        Finding(
            rule_id=rule_id,
            severity=severity,
            confidence=confidence,
            summary=f"{len(overlaps)} {label}" + ("s" if len(overlaps) != 1 else ""),
            explanation=explanation,
            participants=list(participants),
            evidence=[
                {"identity": identity, "references": [item.to_dict() for item in group]}
                for identity, group in sorted(overlaps, key=lambda item: item[0].casefold())
            ],
        )
        for participants, overlaps in sorted(
            aggregated.items(), key=lambda item: tuple(name.casefold() for name in item[0])
        )
    ]


def analyze_cet_references(
    documents: Iterable[CETDocument], references: Iterable[Reference]
) -> list[Finding]:
    document_list = list(documents)
    reference_list = list(references)
    _mark_reachable_and_resolve_modules(document_list, reference_list)
    active = [reference for reference in reference_list if _active(reference)]
    effective = [reference for reference in active if reference.details.get("reachable")]
    findings: list[Finding] = []

    entries_by_root: dict[str, list[Reference]] = defaultdict(list)
    for reference in reference_list:
        if reference.kind == "mod.entry":
            entries_by_root[reference.identity.casefold()].append(reference)
    for group in entries_by_root.values():
        if len(group) < 2:
            continue
        winner = next((item for item in group if _active(item)), None)
        losers = [item for item in group if not _active(item)]
        if winner is not None and losers:
            findings.append(
                Finding(
                    rule_id="CET-ENTRY-OVERRIDE",
                    severity="info",
                    confidence="high",
                    summary=f"CET entry winner selected for {winner.identity}",
                    explanation=(
                        "Multiple Vortex packages provide the same CET mod root and init.lua. "
                        "CET can load only the deployed entry; Vortex's selected winner is active."
                    ),
                    participants=sorted({item.mod_name for item in group}, key=str.casefold),
                    evidence=[item.to_dict() for item in group],
                )
            )

    event_groups: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    for reference in effective:
        event = reference.details.get("event")
        if reference.kind == "event.registration" and event:
            event_groups[(reference.details["mod_root"].casefold(), event)].append(reference)
            if event not in KNOWN_EVENTS:
                findings.append(
                    Finding(
                        rule_id="CET-EVENT-UNKNOWN",
                        severity="error",
                        confidence="high",
                        summary=f"Unknown CET event: {event}",
                        explanation="Current CET rejects unknown registerForEvent names and writes an error to the mod log.",
                        participants=[reference.mod_name],
                        evidence=[reference.to_dict()],
                    )
                )
    duplicate_events = [
        (f"{group[0].details['mod_root']}:{event}", group)
        for (_, event), group in event_groups.items()
        if len(group) > 1 and sum(bool(item.details.get("top_level")) for item in group) > 1
    ]
    findings.extend(_aggregate(
        duplicate_events,
        "CET-EVENT-CALLBACK-REPLACED",
        "warning",
        "high",
        "CET event callback overwrite",
        "A CET ScriptContext stores one callback per lifecycle event. Each later registration replaces the previous callback in the same mod sandbox, so earlier top-level listeners do not run.",
    ))

    binding_groups: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    invalid_bindings: list[Reference] = []
    empty_labels: list[Reference] = []
    for reference in effective:
        binding_id = reference.details.get("binding_id")
        if reference.kind not in {"binding.hotkey", "binding.input"} or binding_id is None:
            continue
        binding_groups[(reference.details["mod_root"].casefold(), binding_id)].append(reference)
        if not _BINDING_ID.fullmatch(binding_id):
            invalid_bindings.append(reference)
        if reference.details.get("display_name") == "":
            empty_labels.append(reference)
    duplicate_bindings = [
        (f"{group[0].details['mod_root']}:{binding_id}", group)
        for (_, binding_id), group in binding_groups.items()
        if len(group) > 1
    ]
    findings.extend(_aggregate(
        duplicate_bindings,
        "CET-BINDING-ID-DUPLICATE",
        "error",
        "high",
        "duplicate CET binding ID",
        "CET requires hotkey and input IDs to be unique inside a mod sandbox and rejects every later registration with the same ID, even when the registration types differ.",
    ))
    for rule_id, label, group in (
        ("CET-BINDING-ID-INVALID", "invalid CET binding ID", invalid_bindings),
        ("CET-BINDING-LABEL-EMPTY", "empty CET binding label", empty_labels),
    ):
        if group:
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity="error",
                    confidence="high",
                    summary=f"{len(group)} {label}" + ("s" if len(group) != 1 else ""),
                    explanation="Current CET rejects this binding registration before adding it to the mod's binding list.",
                    participants=sorted({item.mod_name for item in group}, key=str.casefold),
                    evidence=[item.to_dict() for item in group],
                )
            )

    missing_modules = [
        reference for reference in effective
        if reference.kind == "module.require" and reference.details.get("resolved") is False
    ]
    if missing_modules:
        findings.append(
            Finding(
                rule_id="CET-MODULE-MISSING",
                severity="warning",
                confidence="high",
                summary=f"{len(missing_modules)} literal Lua module path" + ("s do" if len(missing_modules) != 1 else " does") + " not resolve",
                explanation="CET resolves require paths only inside the calling mod root, trying the exact path, a .lua suffix, and an init.lua below that path. These literal paths match none of those deployed files.",
                participants=sorted({item.mod_name for item in missing_modules}, key=str.casefold),
                evidence=[item.to_dict() for item in missing_modules],
            )
        )
    cross_package_modules = [
        reference for reference in effective
        if reference.kind == "module.require"
        and reference.details.get("resolved")
        and reference.details.get("provider_mod_name") != reference.mod_name
    ]
    if cross_package_modules:
        findings.append(
            Finding(
                rule_id="CET-MODULE-CROSS-PACKAGE",
                severity="info",
                confidence="high",
                summary=f"{len(cross_package_modules)} Lua module import" + ("s use" if len(cross_package_modules) != 1 else " uses") + " another Vortex package in the same CET root",
                explanation="CET sees one merged mod root. The deployed entry imports these modules from files supplied by a different Vortex package, creating an explicit package-level dependency inside that root.",
                participants=sorted(
                    {name for item in cross_package_modules for name in (item.mod_name, item.details["provider_mod_name"])},
                    key=str.casefold,
                ),
                evidence=[item.to_dict() for item in cross_package_modules],
            )
        )

    installed_roots = {
        reference.identity for reference in active if reference.kind == "mod.entry"
    }
    installed_roots_casefold = {root.casefold(): root for root in installed_roots}
    missing_mod_dependencies = [
        reference for reference in effective
        if reference.kind == "mod.dependency"
        and str(reference.details.get("target_mod_root", "")).casefold() not in installed_roots_casefold
    ]
    if missing_mod_dependencies:
        findings.append(
            Finding(
                rule_id="CET-GETMOD-TARGET-MISSING",
                severity="review",
                confidence="high",
                summary=f"{len(missing_mod_dependencies)} GetMod target" + ("s are" if len(missing_mod_dependencies) != 1 else " is") + " not installed",
                explanation="GetMod returns nil when the exact CET mod-root name is absent. These dependencies may be optional and guarded, so review the surrounding Lua before treating them as failures.",
                participants=sorted({item.mod_name for item in missing_mod_dependencies}, key=str.casefold),
                evidence=[item.to_dict() for item in missing_mod_dependencies],
            )
        )

    hooks_by_identity: dict[str, list[Reference]] = defaultdict(list)
    for reference in effective:
        if reference.kind.startswith("hook.") and reference.kind != "hook.dynamic":
            hooks_by_identity[reference.identity].append(reference)
    shared_observers: list[tuple[str, list[Reference]]] = []
    compatible_overrides: list[tuple[str, list[Reference]]] = []
    duplicate_overrides: list[tuple[str, list[Reference]]] = []
    terminated_overrides: list[tuple[str, list[Reference]]] = []
    for identity, group in hooks_by_identity.items():
        mods = {item.details.get("mod_root", "").casefold() for item in group}
        if len(mods) < 2:
            continue
        overrides = [item for item in group if item.kind == "hook.override"]
        observers = [item for item in group if item.kind in {"hook.observe_before", "hook.observe_after"}]
        if len({item.details.get("mod_root", "").casefold() for item in observers}) > 1:
            shared_observers.append((identity, observers))
        if len({item.details.get("mod_root", "").casefold() for item in overrides}) > 1:
            if all(item.details.get("calls_wrapped") is True for item in overrides):
                compatible_overrides.append((identity, overrides))
            elif len({item.details.get("body_fingerprint") for item in overrides}) == 1 and all(
                item.details.get("body_fingerprint") for item in overrides
            ):
                duplicate_overrides.append((identity, overrides))
            else:
                terminated_overrides.append((identity, overrides))
    findings.extend(_aggregate(
        shared_observers,
        "CET-OBSERVER-SHARED",
        "info",
        "high",
        "shared additive CET observer target",
        "CET retains all Observe/ObserveBefore/ObserveAfter callbacks for a target. These cross-mod observers are additive; callback side effects can still be inspected in the attached sources.",
    ))
    findings.extend(_aggregate(
        compatible_overrides,
        "CET-OVERRIDE-CHAIN",
        "info",
        "high",
        "compatible CET override chain",
        "CET chains multiple overrides for the same class and method in reverse registration order. Every inline callback calls its final wrapped/next parameter, so inner overrides and the original method remain reachable.",
    ))
    findings.extend(_aggregate(
        duplicate_overrides,
        "CET-OVERRIDE-CHAIN-DUPLICATE",
        "info",
        "high",
        "duplicate CET override chain",
        "These CET overrides have the same normalized inline callback. A callback that does not call its wrapped/next parameter terminates the chain, but the outer duplicate supplies equivalent behavior.",
    ))
    findings.extend(_aggregate(
        terminated_overrides,
        "CET-OVERRIDE-CHAIN-REVIEW",
        "review",
        "medium",
        "CET override chain requiring manual inspection",
        "Multiple CET mods override this class and method. At least one callback is dynamic or does not visibly call its final wrapped/next parameter, so the scanner cannot prove that inner overrides and the original method remain reachable.",
    ))

    settings_by_path: dict[str, list[Reference]] = defaultdict(list)
    for reference in effective:
        if reference.kind.startswith("settings.") and reference.kind != "settings.dynamic":
            settings_by_path[reference.identity].append(reference)
    shared_settings_containers = [
        (identity, group) for identity, group in settings_by_path.items()
        if len({item.details.get("mod_root", "").casefold() for item in group}) > 1
        and all(item.kind in {"settings.addTab", "settings.addSubcategory"} for item in group)
    ]
    shared_settings_controls = [
        (identity, group) for identity, group in settings_by_path.items()
        if len({item.details.get("mod_root", "").casefold() for item in group}) > 1
        and any(item.kind not in {"settings.addTab", "settings.addSubcategory"} for item in group)
    ]
    findings.extend(_aggregate(
        shared_settings_containers,
        "CET-SETTINGS-CONTAINER-SHARED",
        "info",
        "high",
        "shared native-settings container",
        "Different CET mod roots register the same literal Native Settings tab or subcategory. Shared containers are a normal way to group related settings; child control identities are compared separately.",
    ))
    findings.extend(_aggregate(
        shared_settings_controls,
        "CET-SETTINGS-CONTROL-SHARED",
        "review",
        "medium",
        "shared native-settings control",
        "Different CET mod roots register a control at the same literal Native Settings path. Duplicate control types, values, or callbacks can overwrite UI state and should be reviewed.",
    ))
    return findings


def build_cet_coverage(
    documents: Iterable[CETDocument], references: Iterable[Reference]
) -> dict[str, Any]:
    document_list = list(documents)
    reference_list = list(references)
    active = [reference for reference in reference_list if _active(reference)]
    effective = [reference for reference in active if reference.details.get("reachable")]
    counts = Counter(reference.kind for reference in effective)
    roots = {
        reference.identity for reference in active if reference.kind == "mod.entry"
    }
    dynamic = sum(
        counts[kind] for kind in (
            "event.dynamic", "binding.dynamic", "hook.dynamic", "module.dynamic",
            "mod.dependency_dynamic", "settings.dynamic",
        )
    )
    unresolved_modules = sum(
        reference.kind == "module.require" and reference.details.get("resolved") is False
        for reference in effective
    )
    shared_hooks = sum(
        len({item.details.get("mod_root", "").casefold() for item in group}) > 1
        for group in _group_by_identity(
            [item for item in effective if item.kind.startswith("hook.") and item.kind != "hook.dynamic"]
        ).values()
    )
    return {
        "documents": len(document_list),
        "sections": [
            {
                "name": "CET Lua mod roots and entrypoints",
                "documents": len(roots),
                "status": "analyzed",
                "note": "Deployed and Vortex-overridden init.lua entries are separated; literal require paths are resolved within each CET sandbox root.",
            },
            {
                "name": "CET registrations and hooks",
                "documents": sum(bool(document.call_counts) for document in document_list),
                "status": "partial" if dynamic else "analyzed",
                "note": "Literal lifecycle events, bindings, dependencies, Native Settings paths, observers, and overrides are extracted. Dynamic argument construction remains inventoried but not compared.",
            },
        ],
        "registration_operations": [
            {
                "name": "CET Lua API registrations",
                "status": "partial" if dynamic else "analyzed",
                "documents": len(document_list),
                "mod_roots": len(roots),
                "entrypoints": counts["mod.entry"],
                "events": counts["event.registration"],
                "hotkeys": counts["binding.hotkey"],
                "inputs": counts["binding.input"],
                "requires": counts["module.require"],
                "getmod_dependencies": counts["mod.dependency"],
                "observers": counts["hook.observe_before"] + counts["hook.observe_after"],
                "overrides": counts["hook.override"],
                "settings": sum(value for kind, value in counts.items() if kind.startswith("settings.") and kind != "settings.dynamic"),
                "dynamic_calls": dynamic,
                "unresolved_modules": unresolved_modules,
                "shared_hook_targets": shared_hooks,
                "inactive_references": len(reference_list) - len(active),
                "note": "Binding validity follows the installed CET source; observer and override overlaps use CET's additive and chained execution semantics.",
            }
        ],
    }


def _group_by_identity(references: Iterable[Reference]) -> dict[str, list[Reference]]:
    groups: dict[str, list[Reference]] = defaultdict(list)
    for reference in references:
        groups[reference.identity].append(reference)
    return groups
