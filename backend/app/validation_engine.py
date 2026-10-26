"""Deterministic evaluation of reviewed rule definitions and document consistency."""

from dataclasses import dataclass, field
from datetime import date
import json
import re
from typing import Any

from app.models import (
    ApplicationRecord,
    DocumentExtractionRecord,
    DocumentMetadata,
    InstitutionalReferenceRecord,
    RegulatoryRule,
    RegulatorySource,
)

ALLOWED_DOCUMENT_CATEGORIES = {
    "affiliation_certificate", "fire_safety", "building_completion", "faculty_list",
    "land_document", "audited_accounts",
}
ALLOWED_FIELDS = {
    "institution_name", "institution_id", "document_type", "document_reference_number",
    "issue_date", "expiry_date", "issuer", "faculty_count",
}
ALLOWED_SEVERITIES = {"High", "Medium", "Low"}


@dataclass
class Evaluation:
    issue_key: str
    source_kind: str
    rule_id: str
    rule_version: int | None
    rule_name: str
    result_status: str
    severity: str
    expected: str | None
    actual: str | None
    document_ids: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


def _field_values(document: Any) -> dict[str, dict[str, Any]]:
    record = None
    # Only use validated completed/partial/uncertain structured extraction outputs.
    rows = sorted(
        document.structured_extractions,
        key=lambda item: (item.created_at, item.id),
        reverse=True,
    )
    for candidate in rows:
        if candidate.status in {"complete", "partial", "uncertain"} and candidate.result_json:
            record = candidate.result_json
            break
    if not record:
        return {}
    values: dict[str, dict[str, Any]] = {}
    for field_name in ALLOWED_FIELDS:
        item = record.get(field_name)
        if not isinstance(item, dict) or item.get("value") is None:
            continue
        values[field_name] = {
            "value": item.get("value"),
            "evidence": item.get("evidence"),
            "page_number": item.get("page_number"),
            "document_id": document.id,
            "base_document_id": getattr(document, "base_document_id", document.id),
        }
    return values


def _severity(parameters: dict) -> str:
    if not isinstance(parameters, dict):
        return "Medium"
    value = parameters.get("severity", "Medium")
    return value if value in ALLOWED_SEVERITIES else "Medium"


def _unknown_parameters(parameters: dict, allowed: set[str]) -> bool:
    return bool(set(parameters) - allowed)


def _result(
    rule: RegulatoryRule,
    status: str,
    message: str,
    *,
    expected: str | None = None,
    actual: str | None = None,
    documents: list[str] | None = None,
    evidence: list[dict] | None = None,
    issue_suffix: str = "result",
    severity: str | None = None,
) -> Evaluation:
    return Evaluation(
        issue_key=f"rule:{rule.rule_id}:v{rule.version}:{issue_suffix}",
        source_kind="regulatory",
        rule_id=rule.rule_id,
        rule_version=rule.version,
        rule_name=rule.rule_title,
        result_status=status,
        severity=severity or _severity(rule.validation_parameters),
        expected=expected,
        actual=actual,
        document_ids=documents or [],
        evidence=evidence or [],
        message=message,
    )


def evaluate_rule(
    rule: RegulatoryRule,
    documents: list[Any],
    application: ApplicationRecord,
    today: date,
    authorized_reference_records: list[InstitutionalReferenceRecord] | None = None,
) -> Evaluation:
    parameters = rule.validation_parameters or {}
    if rule.conditions:
        return _result(rule, "manual_review", "Rule conditions are not supported by this deterministic engine.", issue_suffix="unsupported-conditions")
    if not isinstance(parameters, dict):
        return _result(rule, "manual_review", "Rule parameters are malformed and require manual review.", issue_suffix="malformed-parameters")

    validation_type = rule.validation_type
    common = {"severity"}
    if validation_type == "manual_review":
        return _result(rule, "manual_review", "This verified rule is configured for human review.", issue_suffix="manual-review")

    category = parameters.get("document_category")
    if category is not None and category not in ALLOWED_DOCUMENT_CATEGORIES:
        return _result(rule, "manual_review", "The rule names an unsupported document category.", issue_suffix="unsupported-category")
    matching = [document for document in documents if category is None or document.category == category]
    field_name = parameters.get("field")
    if field_name is not None and field_name not in ALLOWED_FIELDS:
        return _result(rule, "manual_review", "The rule names an unsupported field.", issue_suffix="unsupported-field")

    if validation_type == "presence":
        allowed = common | {"document_category", "field"}
        if _unknown_parameters(parameters, allowed) or (category is None and field_name is None):
            return _result(rule, "manual_review", "Presence rule parameters are incomplete or unsupported.", issue_suffix="invalid-presence-config")
        if category is not None and not matching:
            return _result(
                rule, "mismatch", "A required document is missing.", expected=category, actual="missing",
                issue_suffix=f"document-presence:{category}",
            )
        if field_name is not None:
            observed = [
                (document, _field_values(document).get(field_name))
                for document in matching
            ]
            present = [(doc, value) for doc, value in observed if value is not None]
            if not present:
                return _result(
                    rule, "unable_to_verify", "The required field is not available in extracted document data.",
                    expected=field_name, actual=None, documents=[doc.id for doc, _ in observed],
                    issue_suffix=f"field-presence:{category or '*'}:{field_name}",
                )
            return _result(
                rule, "pass", "The required document field is present.", expected=field_name,
                actual=json.dumps([entry[1]["value"] for entry in present], ensure_ascii=False),
                documents=[doc.id for doc, _ in present], evidence=[entry[1] for entry in present],
                issue_suffix=f"field-presence:{category or '*'}:{field_name}",
            )
        return _result(rule, "pass", "The required document is present.", expected=category, actual=category,
                       documents=[doc.id for doc in matching], issue_suffix=f"present-document:{category}")

    if validation_type == "date":
        allowed = common | {"document_category", "field", "comparison", "date"}
        comparison = parameters.get("comparison", "not_expired")
        if (
            _unknown_parameters(parameters, allowed)
            or category is None
            or field_name not in {"issue_date", "expiry_date"}
            or comparison not in {"not_expired", "not_before", "not_after"}
        ):
            return _result(rule, "manual_review", "Date rule parameters are incomplete or unsupported.", issue_suffix="invalid-date-config")
        if not matching:
            return _result(rule, "unable_to_verify", "No document is available for the date check.", expected=category, actual="missing",
                           issue_suffix=f"date:{category}:{field_name}:{comparison}")
        available = [(doc, _field_values(doc).get(field_name)) for doc in matching]
        available = [(doc, value) for doc, value in available if value is not None]
        if not available:
            return _result(rule, "unable_to_verify", "The required date was not extracted.", expected=field_name,
                           documents=[doc.id for doc in matching], issue_suffix=f"date:{category}:{field_name}:{comparison}")
        threshold = parameters.get("date")
        if comparison != "not_expired":
            try:
                threshold = date.fromisoformat(str(threshold))
            except (TypeError, ValueError):
                return _result(rule, "manual_review", "Date comparison requires a valid ISO date parameter.", issue_suffix="invalid-date-threshold")
        outcomes = []
        for document, item in available:
            try:
                observed = date.fromisoformat(str(item["value"]))
            except ValueError:
                continue
            passed = (
                observed >= today if comparison == "not_expired"
                else observed >= threshold if comparison == "not_before"
                else observed <= threshold
            )
            outcomes.append((document, item, observed, passed))
        if not outcomes:
            return _result(rule, "unable_to_verify", "The extracted date could not be parsed safely.", expected=comparison,
                           documents=[doc.id for doc, _ in available], issue_suffix=f"date:{category}:{field_name}:{comparison}")
        passed = all(item[3] for item in outcomes)
        return _result(
            rule, "pass" if passed else "mismatch",
            "The date meets the configured condition." if passed else "The extracted date does not meet the configured condition.",
            expected=f"{comparison}:{threshold.isoformat() if hasattr(threshold, 'isoformat') else threshold}",
            actual=json.dumps([item[2].isoformat() for item in outcomes]),
            documents=[item[0].id for item in outcomes], evidence=[item[1] for item in outcomes],
            issue_suffix=f"date:{category}:{field_name}:{comparison}",
        )

    if validation_type in {"numeric", "text_match"}:
        allowed = common | {"document_category", "field", "comparison", "expected", "reference_record_id"}
        if _unknown_parameters(parameters, allowed) or field_name not in ALLOWED_FIELDS:
            return _result(rule, "manual_review", "Comparison rule parameters are incomplete or unsupported.", issue_suffix=f"invalid-{validation_type}-config")
        expected = parameters.get("expected")
        reference_id = parameters.get("reference_record_id")
        reference = None
        if reference_id is not None:
            reference = next(
                (item for item in (authorized_reference_records or [])
                 if item.institution_id == reference_id and item.is_authorized),
                None,
            )
            if reference is None or reference.institution_id != application.institution_id:
                return _result(rule, "unable_to_verify", "The explicitly referenced institutional record is unavailable or unauthorized.",
                               expected=str(reference_id), issue_suffix=f"unauthorized-reference:{reference_id}")
            expected = (
                reference.faculty_count if field_name == "faculty_count"
                else reference.name if field_name == "institution_name"
                else reference.institution_id if field_name == "institution_id"
                else None
            )
            if expected is None:
                return _result(rule, "manual_review", "The authorized reference record has no supported value for this field.",
                               issue_suffix=f"unsupported-reference-field:{field_name}")
        if expected is None:
            return _result(rule, "manual_review", "Comparison rule has no configured or authorized expected value.", issue_suffix=f"missing-expected:{field_name}")
        available = []
        for document in matching:
            value = _field_values(document).get(field_name)
            if value is not None:
                available.append((document, value))
        if not available:
            return _result(rule, "unable_to_verify", "The comparison field was not extracted from the selected documents.",
                           expected=str(expected), documents=[doc.id for doc in matching],
                           issue_suffix=f"{validation_type}:{category or '*'}:{field_name}:{parameters.get('comparison', 'exact')}")
        comparison = parameters.get("comparison", "exact")
        comparisons = []
        if validation_type == "numeric":
            if field_name != "faculty_count" or comparison not in {"equals", "min", "max"}:
                return _result(rule, "manual_review", "Only faculty_count numeric equals/min/max checks are supported.", issue_suffix="unsupported-numeric-operation")
            try:
                expected_number = float(expected)
                for _document, item in available:
                    actual_number = float(item["value"])
                    passed = (
                        actual_number == expected_number if comparison == "equals"
                        else actual_number >= expected_number if comparison == "min"
                        else actual_number <= expected_number
                    )
                    comparisons.append(passed)
            except (TypeError, ValueError):
                return _result(rule, "manual_review", "Numeric comparison values are malformed.", issue_suffix="invalid-numeric-values")
        else:
            if comparison not in {"exact", "contains"}:
                return _result(rule, "manual_review", "Only exact and contains text comparisons are supported.", issue_suffix="unsupported-text-operation")
            expected_text = str(expected).strip().casefold()
            for _document, item in available:
                actual_text = str(item["value"]).strip().casefold()
                comparisons.append(actual_text == expected_text if comparison == "exact" else expected_text in actual_text)
        passed = all(comparisons)
        reference_evidence = ([{"reference_record_id": reference.institution_id, "source_label": reference.source_label,
                                "authorized": True, "value": expected}] if reference is not None else [])
        return _result(
            rule, "pass" if passed else "mismatch",
            "The configured field comparison passed." if passed else "The configured field comparison did not match.",
            expected=str(expected), actual=json.dumps([item[1]["value"] for item in available], ensure_ascii=False),
            documents=[item[0].id for item in available],
            evidence=[item[1] for item in available] + reference_evidence,
            issue_suffix=f"{validation_type}:{category or '*'}:{field_name}:{comparison}",
            severity=_severity(parameters),
        )

    return _result(rule, "manual_review", "This deterministic validation type is not supported.", issue_suffix="unsupported-type")


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def evaluate_cross_document(documents: list[Any]) -> list[Evaluation]:
    per_field: dict[str, list[dict]] = {}
    for document in documents:
        for name, item in _field_values(document).items():
            per_field.setdefault(name, []).append(item)
    evaluations = []
    for name, values in per_field.items():
        if len(values) < 2:
            continue
        observed = {_normalize(item["value"]) for item in values}
        conflict = len(observed) > 1
        evaluations.append(Evaluation(
            issue_key=f"cross-document:{name}",
            source_kind="cross_document",
            rule_id=f"cross_document.{name}",
            rule_version=None,
            rule_name=f"Cross-document consistency: {name}",
            result_status="manual_review" if conflict else "pass",
            severity="Medium",
            expected=None,
            actual=json.dumps([{"value": item["value"], "document_id": item["document_id"]} for item in values], ensure_ascii=False),
            document_ids=sorted({item["document_id"] for item in values}),
            evidence=values,
            message=(
                f"Documents contain differing {name} values; review the evidence. This is not a fraud determination."
                if conflict else f"The compared {name} values are consistent across available documents."
            ),
        ))
    return evaluations
