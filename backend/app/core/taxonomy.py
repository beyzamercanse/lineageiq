"""Shared incident taxonomy: types, root-cause codes, severity, and their mappings.

Used by injectors, detectors, the agent, validation, and evaluation so the whole system speaks one
vocabulary.
"""

from __future__ import annotations

from enum import Enum


class IncidentType(str, Enum):
    DUPLICATE_TRANSACTION = "duplicate_transaction"
    STALE_FX_RATE = "stale_fx_rate"
    MISSING_CUSTOMER_MAPPING = "missing_customer_mapping"
    SCHEMA_CHANGE = "schema_change"
    DELAYED_PIPELINE = "delayed_pipeline"
    TIMEZONE_CONVERSION_ERROR = "timezone_conversion_error"
    NULL_CONTAMINATION = "null_contamination"
    PARTIAL_LOAD = "partial_load"
    INCORRECT_AGGREGATION = "incorrect_aggregation"
    UPSTREAM_API_FAILURE = "upstream_api_failure"


class RootCauseCode(str, Enum):
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    STALE_FX_RATE = "STALE_FX_RATE"
    MISSING_CUSTOMER_MAPPING = "MISSING_CUSTOMER_MAPPING"
    SCHEMA_CONTRACT_CHANGE = "SCHEMA_CONTRACT_CHANGE"
    DELAYED_PIPELINE = "DELAYED_PIPELINE"
    TIMEZONE_CONVERSION_ERROR = "TIMEZONE_CONVERSION_ERROR"
    NULL_CONTAMINATION = "NULL_CONTAMINATION"
    PARTIAL_LOAD = "PARTIAL_LOAD"
    INCORRECT_AGGREGATION = "INCORRECT_AGGREGATION"
    UPSTREAM_API_FAILURE = "UPSTREAM_API_FAILURE"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


# One incident type maps to exactly one true root-cause code.
INCIDENT_TYPE_TO_ROOT_CAUSE: dict[IncidentType, RootCauseCode] = {
    IncidentType.DUPLICATE_TRANSACTION: RootCauseCode.DUPLICATE_TRANSACTION,
    IncidentType.STALE_FX_RATE: RootCauseCode.STALE_FX_RATE,
    IncidentType.MISSING_CUSTOMER_MAPPING: RootCauseCode.MISSING_CUSTOMER_MAPPING,
    IncidentType.SCHEMA_CHANGE: RootCauseCode.SCHEMA_CONTRACT_CHANGE,
    IncidentType.DELAYED_PIPELINE: RootCauseCode.DELAYED_PIPELINE,
    IncidentType.TIMEZONE_CONVERSION_ERROR: RootCauseCode.TIMEZONE_CONVERSION_ERROR,
    IncidentType.NULL_CONTAMINATION: RootCauseCode.NULL_CONTAMINATION,
    IncidentType.PARTIAL_LOAD: RootCauseCode.PARTIAL_LOAD,
    IncidentType.INCORRECT_AGGREGATION: RootCauseCode.INCORRECT_AGGREGATION,
    IncidentType.UPSTREAM_API_FAILURE: RootCauseCode.UPSTREAM_API_FAILURE,
}

ALL_INCIDENT_TYPES: list[IncidentType] = list(IncidentType)


def root_cause_for(incident_type: IncidentType) -> RootCauseCode:
    return INCIDENT_TYPE_TO_ROOT_CAUSE[incident_type]
