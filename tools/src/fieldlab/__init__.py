"""Tooling for cairn-fieldlab packet logs.

`fieldlab.schema` defines the on-card CSV format. Everything else reads it
through that module rather than hard-coding column names or ranges.
"""

from fieldlab.schema import SCHEMA_VERSION

__all__ = ["SCHEMA_VERSION"]
