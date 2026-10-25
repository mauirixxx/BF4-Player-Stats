"""Parameter-bound multirow VALUES for bounded Battlelog equipment payloads."""

from collections.abc import Mapping, Sequence


def bulk_values(rows: Sequence[Mapping[str, object]], columns: Sequence[str]):
    """Return SQL placeholders and parameters; column names are trusted literals."""
    values = []
    params = {}
    for i, row in enumerate(rows):
        values.append("(" + ", ".join(f":v{i}_{column}" for column in columns) + ")")
        for column in columns:
            params[f"v{i}_{column}"] = row[column]
    return ", ".join(values), params