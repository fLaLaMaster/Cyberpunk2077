from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import Artifact, Finding, Reference


ANNOTATIONS = {
    "wrapMethod": "method.wrap",
    "replaceMethod": "method.replace",
    "addMethod": "method.add",
    "addField": "field.add",
}


@dataclass(frozen=True, slots=True)
class _Token:
    value: str
    line: int
    start: int
    end: int


@dataclass(slots=True)
class RedscriptDocument:
    artifact: Artifact
    annotation_counts: dict[str, int]


def _lex(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    line = 1
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            line += char == "\n"
            index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            if end < 0:
                break
            index = end
            continue
        if source.startswith("/*", index):
            start = index
            depth = 1
            index += 2
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    line += source[index] == "\n"
                    index += 1
            if depth:
                tokens.append(_Token("<unterminated-comment>", line, start, length))
            continue
        if char in {'"', "'"}:
            start = index
            quote = char
            index += 1
            while index < length:
                if source[index] == "\\":
                    index += 2
                    continue
                line += source[index] == "\n"
                index += 1
                if source[index - 1] == quote:
                    break
            tokens.append(_Token(source[start:index], line, start, index))
            continue
        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < length and (source[index].isalnum() or source[index] == "_"):
                index += 1
            tokens.append(_Token(source[start:index], line, start, index))
            continue
        if char.isdigit():
            start = index
            index += 1
            while index < length and (source[index].isalnum() or source[index] in "._"):
                index += 1
            tokens.append(_Token(source[start:index], line, start, index))
            continue
        for operator in ("->", "::", "<=", ">=", "==", "!=", "&&", "||", "+=", "-=", "*=", "/="):
            if source.startswith(operator, index):
                tokens.append(_Token(operator, line, index, index + len(operator)))
                index += len(operator)
                break
        else:
            tokens.append(_Token(char, line, index, index + 1))
            index += 1
    return tokens


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


def _skip_annotation(tokens: list[_Token], index: int) -> int:
    index += 1
    if index < len(tokens):
        index += 1
    if index < len(tokens) and tokens[index].value == "(":
        close = _matching(tokens, index, "(", ")")
        if close is not None:
            return close + 1
    return index


def _annotation_at(tokens: list[_Token], index: int) -> tuple[str, str, int] | None:
    if index + 1 >= len(tokens) or tokens[index].value != "@":
        return None
    name = tokens[index + 1].value
    end = index + 2
    arguments = ""
    if end < len(tokens) and tokens[end].value == "(":
        close = _matching(tokens, end, "(", ")")
        if close is None:
            return None
        arguments = "".join(token.value for token in tokens[end + 1:close])
        end = close + 1
    return name, arguments, end


def _preceding_conditions(tokens: list[_Token], annotation_index: int) -> list[str]:
    conditions: list[str] = []
    cursor = annotation_index
    while cursor >= 4 and tokens[cursor - 1].value == ")":
        depth = 0
        opening = None
        for index in range(cursor - 1, -1, -1):
            if tokens[index].value == ")":
                depth += 1
            elif tokens[index].value == "(":
                depth -= 1
                if depth == 0:
                    opening = index
                    break
        if (
            opening is None
            or opening < 2
            or tokens[opening - 2].value != "@"
            or tokens[opening - 1].value != "if"
        ):
            break
        conditions.append(
            "".join(token.value for token in tokens[opening + 1:cursor - 1])
        )
        cursor = opening - 2
    conditions.reverse()
    return conditions


def _following_conditions(
    tokens: list[_Token], annotation_end: int, declaration_index: int
) -> list[str]:
    conditions: list[str] = []
    index = annotation_end
    while index < declaration_index:
        annotation = _annotation_at(tokens, index)
        if annotation is None:
            index += 1
            continue
        name, arguments, end = annotation
        if name == "if":
            conditions.append(arguments)
        index = end
    return conditions


_MODULE_CONDITION = re.compile(r'^(?P<negated>!)?ModuleExists\("(?P<module>[^"]+)"\)$')


def _condition_state(conditions: list[str], modules: set[str]) -> bool | None:
    unknown = False
    for condition in conditions:
        match = _MODULE_CONDITION.match(condition)
        if not match:
            unknown = True
            continue
        exists = match.group("module") in modules
        if bool(match.group("negated")) == exists:
            return False
    return None if unknown else True


def _declared_modules(tokens: list[_Token]) -> set[str]:
    modules: set[str] = set()
    for index, token in enumerate(tokens[:-1]):
        if token.value != "module":
            continue
        line = token.line
        values: list[str] = []
        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor].line == line:
            value = tokens[cursor].value
            if value == "." or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
                values.append(value)
                cursor += 1
            else:
                break
        if values:
            modules.add("".join(values))
    return modules


def _declaration_start(tokens: list[_Token], index: int) -> tuple[str, int] | None:
    while index < len(tokens):
        value = tokens[index].value
        if value == "@":
            index = _skip_annotation(tokens, index)
            continue
        if value in {"func", "let"}:
            return value, index
        if value in {"{", "}", ";"}:
            return None
        index += 1
    return None


def _split_top_level(tokens: list[_Token], delimiter: str) -> list[list[_Token]]:
    result: list[list[_Token]] = []
    current: list[_Token] = []
    depths = {"(": 0, "[": 0, "<": 0}
    pairs = {")": "(", "]": "[", ">": "<"}
    for token in tokens:
        if token.value in depths:
            depths[token.value] += 1
        elif token.value in pairs and depths[pairs[token.value]]:
            depths[pairs[token.value]] -= 1
        if token.value == delimiter and not any(depths.values()):
            result.append(current)
            current = []
        else:
            current.append(token)
    result.append(current)
    return result


def _canonical_type(tokens: list[_Token]) -> str:
    values = [token.value for token in tokens]
    while values and values[0] in {"opt", "const", "out"}:
        values.pop(0)

    def render(start: int, end: int) -> str:
        parts: list[str] = []
        index = start
        while index < end:
            if values[index] != "[":
                parts.append(values[index])
                index += 1
                continue
            depth = 1
            close = index + 1
            while close < end and depth:
                depth += values[close] == "["
                depth -= values[close] == "]"
                close += 1
            if depth:
                parts.append(values[index])
                index += 1
            else:
                parts.append(f"array<{render(index + 1, close - 1)}>")
                index = close
        return "".join(parts)

    return render(0, len(values)).strip() or "?"


def _parameter_types(tokens: list[_Token]) -> list[str]:
    parameters: list[str] = []
    for segment in _split_top_level(tokens, ","):
        if not segment:
            continue
        depths = {"(": 0, "[": 0, "<": 0}
        colon = None
        end = len(segment)
        for index, token in enumerate(segment):
            if token.value in depths:
                depths[token.value] += 1
            elif token.value in {")": "(", "]": "[", ">": "<"}:
                opening = {")": "(", "]": "[", ">": "<"}[token.value]
                if depths[opening]:
                    depths[opening] -= 1
            elif token.value == ":" and not any(depths.values()):
                colon = index
            elif token.value == "=" and not any(depths.values()):
                end = index
                break
        if colon is None:
            parameters.append("?")
        else:
            parameters.append(_canonical_type(segment[colon + 1:end]))
    return parameters


def _body_details(tokens: list[_Token], start: int) -> tuple[int, int, str]:
    if start >= len(tokens):
        return 0, start, ""
    if tokens[start].value == "{":
        close = _matching(tokens, start, "{", "}")
        if close is None:
            close = len(tokens) - 1
        body = tokens[start + 1:close]
    elif tokens[start].value == "=":
        close = start + 1
        depths = {"(": 0, "[": 0, "<": 0, "{": 0}
        pairs = {")": "(", "]": "[", ">": "<", "}": "{"}
        while close < len(tokens):
            value = tokens[close].value
            if value in depths:
                depths[value] += 1
            elif value in pairs and depths[pairs[value]]:
                depths[pairs[value]] -= 1
            elif value == ";" and not any(depths.values()):
                break
            close += 1
        body = tokens[start + 1:close]
    else:
        return 0, start, ""
    calls = sum(
        token.value == "wrappedMethod"
        and index + 1 < len(body)
        and body[index + 1].value == "("
        for index, token in enumerate(body)
    )
    fingerprint = hashlib.sha256(
        "\x1f".join(token.value for token in body).encode("utf-8")
    ).hexdigest()
    return calls, close, fingerprint


def _function_reference(
    artifact: Artifact,
    annotation: str,
    target: str,
    annotation_line: int,
    tokens: list[_Token],
    func_index: int,
    conditions: list[str],
    condition_state: bool | None,
) -> Reference | None:
    if func_index + 1 >= len(tokens):
        return None
    name_token = tokens[func_index + 1]
    open_index = func_index + 2
    while open_index < len(tokens) and tokens[open_index].value != "(":
        if tokens[open_index].value in {"{", "}", ";"}:
            return None
        open_index += 1
    if open_index >= len(tokens):
        return None
    close_index = _matching(tokens, open_index, "(", ")")
    if close_index is None:
        return None
    params = _parameter_types(tokens[open_index + 1:close_index])
    return_type = "Void"
    body_index = close_index + 1
    if body_index < len(tokens) and tokens[body_index].value == "->":
        type_start = body_index + 1
        body_index = type_start
        while body_index < len(tokens) and tokens[body_index].value not in {"{", "=", ";", "where"}:
            body_index += 1
        return_type = _canonical_type(tokens[type_start:body_index])
        if body_index < len(tokens) and tokens[body_index].value == "where":
            while body_index < len(tokens) and tokens[body_index].value not in {"{", "=", ";"}:
                body_index += 1
    else:
        while body_index < len(tokens) and tokens[body_index].value not in {"{", "=", ";"}:
            body_index += 1

    qualifiers = {token.value for token in tokens[max(0, func_index - 10):func_index]}
    declared_return_type = return_type
    if "cb" in qualifiers and return_type == "Void":
        # redscript explicitly retries callback annotations as Bool for legacy mods.
        return_type = "Bool"
    wrapped_calls, _body_end, body_fingerprint = _body_details(tokens, body_index)
    signature = f"{name_token.value}({','.join(params)})->{return_type}"
    identity = f"{target}.{signature}"
    return Reference(
        ecosystem="redscript",
        kind=ANNOTATIONS[annotation],
        identity=identity,
        mod_name=artifact.mod_name,
        source_path=str(artifact.absolute_path),
        line=annotation_line,
        details={
            "annotation": annotation,
            "target_class": target,
            "method_name": name_token.value,
            "parameter_types": params,
            "return_type": return_type,
            "declared_return_type": declared_return_type,
            "signature": signature,
            "declaration_line": name_token.line,
            "wrapped_method_calls": wrapped_calls,
            "calls_wrapped_method": wrapped_calls > 0,
            "body_fingerprint": body_fingerprint,
            "relative_path": artifact.relative_path,
            "deployed_state": artifact.deployed_state,
            "conditions": conditions,
            "condition_state": condition_state,
        },
    )


def _field_reference(
    artifact: Artifact,
    annotation: str,
    target: str,
    annotation_line: int,
    tokens: list[_Token],
    let_index: int,
    conditions: list[str],
    condition_state: bool | None,
) -> Reference | None:
    if let_index + 2 >= len(tokens):
        return None
    name_token = tokens[let_index + 1]
    colon = let_index + 2
    while colon < len(tokens) and tokens[colon].value not in {":", ";", "{"}:
        colon += 1
    if colon >= len(tokens) or tokens[colon].value != ":":
        return None
    end = colon + 1
    while end < len(tokens) and tokens[end].value not in {"=", ";", "{"}:
        end += 1
    field_type = _canonical_type(tokens[colon + 1:end])
    return Reference(
        ecosystem="redscript",
        kind=ANNOTATIONS[annotation],
        identity=f"{target}.{name_token.value}",
        mod_name=artifact.mod_name,
        source_path=str(artifact.absolute_path),
        line=annotation_line,
        details={
            "annotation": annotation,
            "target_class": target,
            "field_name": name_token.value,
            "field_type": field_type,
            "declaration_line": name_token.line,
            "relative_path": artifact.relative_path,
            "deployed_state": artifact.deployed_state,
            "conditions": conditions,
            "condition_state": condition_state,
        },
    )


def parse_redscript_documents(
    artifacts: Iterable[Artifact],
) -> tuple[list[RedscriptDocument], list[Reference], list[Finding]]:
    documents: list[RedscriptDocument] = []
    references: list[Reference] = []
    findings: list[Finding] = []
    loaded: list[tuple[Artifact, list[_Token]]] = []
    for artifact in artifacts:
        if artifact.extension.casefold() != ".reds":
            continue
        try:
            source = artifact.absolute_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            findings.append(
                Finding(
                    rule_id="RS-FILE-READ-ERROR",
                    severity="error",
                    confidence="high",
                    summary=f"REDscript file could not be read: {artifact.relative_path}",
                    explanation=str(exc),
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
            continue
        loaded.append((artifact, _lex(source)))

    modules = {
        module
        for loaded_artifact, tokens in loaded
        if loaded_artifact.deployed_state != "overridden"
        for module in _declared_modules(tokens)
    }
    for artifact, tokens in loaded:
        counts: Counter[str] = Counter()
        parse_evidence: list[dict[str, Any]] = []
        index = 0
        while index + 3 < len(tokens):
            if tokens[index].value != "@" or tokens[index + 1].value not in ANNOTATIONS:
                index += 1
                continue
            annotation = tokens[index + 1].value
            annotation_line = tokens[index].line
            counts[annotation] += 1
            if tokens[index + 2].value != "(":
                close = None
            else:
                close = _matching(tokens, index + 2, "(", ")")
            if close is None:
                parse_evidence.append({
                    "path": str(artifact.absolute_path),
                    "line": annotation_line,
                    "annotation": annotation,
                    "reason": "annotation target parentheses are malformed",
                })
                index += 2
                continue
            target = "".join(token.value for token in tokens[index + 3:close]).strip()
            declaration = _declaration_start(tokens, close + 1)
            reference = None
            if target and declaration is not None:
                kind, declaration_index = declaration
                conditions = [
                    *_preceding_conditions(tokens, index),
                    *_following_conditions(tokens, close + 1, declaration_index),
                ]
                condition_state = _condition_state(conditions, modules)
                if kind == "func" and annotation != "addField":
                    reference = _function_reference(
                        artifact, annotation, target, annotation_line,
                        tokens, declaration_index, conditions, condition_state,
                    )
                elif kind == "let" and annotation == "addField":
                    reference = _field_reference(
                        artifact, annotation, target, annotation_line,
                        tokens, declaration_index, conditions, condition_state,
                    )
            if reference is None:
                parse_evidence.append({
                    "path": str(artifact.absolute_path),
                    "line": annotation_line,
                    "annotation": annotation,
                    "target": target,
                    "reason": "a matching method or field declaration was not parsed",
                })
            else:
                references.append(reference)
            index = close + 1
        documents.append(RedscriptDocument(artifact, dict(counts)))
        if parse_evidence:
            findings.append(
                Finding(
                    rule_id="RS-ANNOTATION-PARSE-ERROR",
                    severity="error",
                    confidence="high",
                    summary=f"REDscript annotations could not be parsed: {len(parse_evidence)} occurrence(s)",
                    explanation=(
                        "The scanner found a supported REDscript annotation but could not "
                        "pair it with its target declaration. The compiler may also reject "
                        "this shape; the affected symbol was excluded from static comparison."
                    ),
                    participants=[artifact.mod_name],
                    evidence=parse_evidence,
                )
            )
    return documents, references, findings


def _aggregate_overlap(
    groups: Iterable[tuple[str, list[Reference]]],
    rule_id: str,
    severity: str,
    summary_label: str,
    explanation: str,
) -> list[Finding]:
    aggregate: dict[tuple[str, ...], list[tuple[str, list[Reference]]]] = defaultdict(list)
    for identity, group in groups:
        participants = tuple(sorted({item.mod_name for item in group}, key=str.casefold))
        aggregate[participants].append((identity, group))
    return [
        Finding(
            rule_id=rule_id,
            severity=severity,
            confidence="high",
            summary=f"{len(overlaps)} {summary_label}" + ("s" if len(overlaps) != 1 else ""),
            explanation=explanation,
            participants=list(participants),
            evidence=[
                {
                    "identity": identity,
                    "references": [reference.to_dict() for reference in group],
                }
                for identity, group in sorted(overlaps, key=lambda item: item[0])
            ],
        )
        for participants, overlaps in sorted(
            aggregate.items(), key=lambda item: tuple(name.casefold() for name in item[0])
        )
    ]


def compare_redscript_references(references: Iterable[Reference]) -> list[Finding]:
    reference_list = [
        reference
        for reference in references
        if _reference_is_active(reference)
    ]
    by_kind_identity: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    by_identity: dict[str, list[Reference]] = defaultdict(list)
    for reference in reference_list:
        by_kind_identity[(reference.kind, reference.identity)].append(reference)
        by_identity[reference.identity].append(reference)

    findings: list[Finding] = []
    replacement_conflicts: list[tuple[str, list[Reference]]] = []
    replacement_duplicates: list[tuple[str, list[Reference]]] = []
    for (kind, identity), group in by_kind_identity.items():
        if kind != "method.replace" or len(group) < 2:
            continue
        fingerprints = {item.details.get("body_fingerprint") for item in group}
        if len(fingerprints) == 1:
            replacement_duplicates.append((identity, group))
        else:
            replacement_conflicts.append((identity, group))
    findings.extend(_aggregate_overlap(
        replacement_conflicts,
        "RS-METHOD-REPLACEMENT-CONFLICT",
        "conflict",
        "competing method replacement",
        "Only one @replaceMethod annotation can be active for an exact class and method signature. These replacements have different bodies, so the later annotation overwrites behavior from the earlier mod.",
    ))
    findings.extend(_aggregate_overlap(
        replacement_duplicates,
        "RS-METHOD-REPLACEMENT-DUPLICATE",
        "warning",
        "duplicate method replacement",
        "Only one @replaceMethod annotation can be active, but these normalized method bodies are identical. The compiler still reports an overwrite; the final replacement behavior is equivalent.",
    ))

    added_methods = [
        (identity, group)
        for (kind, identity), group in by_kind_identity.items()
        if kind == "method.add" and len(group) > 1
    ]
    findings.extend(_aggregate_overlap(
        added_methods,
        "RS-ADDED-METHOD-CONFLICT",
        "conflict",
        "duplicate added method",
        "These @addMethod annotations define the same class, name, parameter types, and return type. REDscript cannot add the same method signature more than once.",
    ))

    field_conflicts: list[tuple[str, list[Reference]]] = []
    field_duplicates: list[tuple[str, list[Reference]]] = []
    for (kind, identity), group in by_kind_identity.items():
        if kind != "field.add" or len(group) < 2:
            continue
        types = {item.details.get("field_type") for item in group}
        (field_duplicates if len(types) == 1 else field_conflicts).append((identity, group))
    findings.extend(_aggregate_overlap(
        field_conflicts,
        "RS-ADDED-FIELD-CONFLICT",
        "conflict",
        "incompatible added field",
        "These @addField annotations use the same target class and field name but disagree on the type. The later field addition has no effect and code can observe the wrong field type.",
    ))
    findings.extend(_aggregate_overlap(
        field_duplicates,
        "RS-ADDED-FIELD-DUPLICATE",
        "warning",
        "duplicate added field",
        "These @addField annotations repeat the same target class, name, and type. REDscript keeps the first field and warns that later additions have no effect.",
    ))

    added_annotation_conflicts: list[tuple[str, list[Reference]]] = []
    for identity, group in by_identity.items():
        add_mods = {item.mod_name for item in group if item.kind == "method.add"}
        annotation_mods = {
            item.mod_name
            for item in group
            if item.kind in {"method.wrap", "method.replace"}
        }
        if add_mods and annotation_mods and any(a != b for a in add_mods for b in annotation_mods):
            added_annotation_conflicts.append((identity, group))
    findings.extend(_aggregate_overlap(
        added_annotation_conflicts,
        "RS-ANNOTATES-ADDED-METHOD",
        "conflict",
        "annotation targeting an added method",
        "One mod adds this method while another wraps or replaces the same signature. REDscript forbids annotations that modify user-defined symbols, so this combination cannot compile reliably.",
    ))

    shared_wrapper_groups = [
        (identity, group)
        for (kind, identity), group in by_kind_identity.items()
        if kind == "method.wrap"
        and len({item.mod_name for item in group}) > 1
    ]
    wrapper_chains = [
        (identity, group)
        for identity, group in shared_wrapper_groups
        if all(item.details.get("calls_wrapped_method") for item in group)
    ]
    terminated_wrapper_chains = [
        (identity, group)
        for identity, group in shared_wrapper_groups
        if not all(item.details.get("calls_wrapped_method") for item in group)
    ]
    findings.extend(_aggregate_overlap(
        wrapper_chains,
        "RS-WRAPPER-CHAIN",
        "info",
        "compatible wrapper chain",
        "REDscript supports multiple @wrapMethod annotations on one exact signature and chains them. Every listed wrapper invokes wrappedMethod, so the earlier implementations remain reachable.",
    ))
    findings.extend(_aggregate_overlap(
        terminated_wrapper_chains,
        "RS-WRAPPER-CHAIN-TERMINATED",
        "warning",
        "terminated wrapper chain",
        "Multiple mods wrap this exact signature, but at least one wrapper never calls wrappedMethod. Wrappers or the original implementation below that point are suppressed, and which behavior remains reachable depends on annotation order.",
    ))

    wrappers_without_call: dict[str, list[Reference]] = defaultdict(list)
    for reference in reference_list:
        if reference.kind == "method.wrap" and not reference.details.get("calls_wrapped_method"):
            wrappers_without_call[reference.mod_name].append(reference)
    for mod_name, group in sorted(wrappers_without_call.items(), key=lambda item: item[0].casefold()):
        findings.append(
            Finding(
                rule_id="RS-WRAPPER-SKIPS-WRAPPED-METHOD",
                severity="review",
                confidence="high",
                summary=f"{len(group)} wrappers do not invoke wrappedMethod",
                explanation=(
                    "A @wrapMethod body that never calls wrappedMethod terminates the wrapper "
                    "chain and suppresses the original method plus wrappers below it. This can "
                    "be intentional, but it should be reviewed when compatibility is expected."
                ),
                participants=[mod_name],
                evidence=[reference.to_dict() for reference in group],
            )
        )
    return findings


def build_redscript_coverage(
    documents: Iterable[RedscriptDocument], references: Iterable[Reference]
) -> dict[str, Any]:
    document_list = list(documents)
    reference_list = list(references)
    active_references = [
        reference
        for reference in reference_list
        if _reference_is_active(reference)
    ]
    counts = Counter(reference.kind for reference in active_references)
    inactive = len(reference_list) - len(active_references)
    annotated_documents = sum(bool(document.annotation_counts) for document in document_list)
    shared_wrappers = sum(
        len({item.mod_name for item in group}) > 1
        for group in _groups(active_references, "method.wrap").values()
    )
    shared_replacements = sum(
        len(group) > 1 for group in _groups(active_references, "method.replace").values()
    )
    compatible_wrapper_chains = sum(
        len({item.mod_name for item in group}) > 1
        and all(item.details.get("calls_wrapped_method") for item in group)
        for group in _groups(active_references, "method.wrap").values()
    )
    return {
        "documents": len(document_list),
        "sections": [
            {
                "name": "annotated REDscript symbols",
                "documents": annotated_documents,
                "status": "analyzed",
                "note": "Supported annotations are paired with exact class, method parameter/return types, or field names using source-preserving lexical parsing.",
            }
        ],
        "annotation_operations": [
            {
                "name": "REDscript annotations",
                "status": "analyzed",
                "documents": annotated_documents,
                "wrap_methods": counts["method.wrap"],
                "replace_methods": counts["method.replace"],
                "add_methods": counts["method.add"],
                "add_fields": counts["field.add"],
                "shared_wrapper_signatures": shared_wrappers,
                "shared_replacement_signatures": shared_replacements,
                "compatible_wrapper_chains": compatible_wrapper_chains,
                "terminated_wrapper_chains": shared_wrappers - compatible_wrapper_chains,
                "inactive_annotations": inactive,
                "note": "Wrapper chains, replacement overwrites, added-symbol collisions, and wrappers that skip wrappedMethod are classified.",
            }
        ],
    }


def _groups(references: list[Reference], kind: str) -> dict[str, list[Reference]]:
    result: dict[str, list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind == kind:
            result[reference.identity].append(reference)
    return result


def _reference_is_active(reference: Reference) -> bool:
    return (
        reference.details.get("condition_state") is not False
        and reference.details.get("deployed_state") != "overridden"
    )
