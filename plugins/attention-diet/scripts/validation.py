"""Shared schema validation; this module is not a separate command-line helper."""
from functools import lru_cache
import json
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import ValidationError
    from referencing import Registry, Resource
except ImportError as error:
    raise SystemExit(
        "Attention Diet needs its runtime dependencies. Install requirements.txt in the "
        "dedicated environment described in README.md, then use that environment's Python."
    ) from error

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
FORMATS = FormatChecker()
if not {"date-time", "uri"} <= FORMATS.checkers.keys():
    raise SystemExit("Attention Diet needs jsonschema's format-nongpl extra; install requirements.txt.")


@lru_cache(maxsize=1)
def registry():
    # Resolve bundled references locally. Never retrieve a schema from the network.
    resources = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        resources.append((path.as_uri(), Resource.from_contents(schema)))
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def validator(name, fragment=""):
    path = SCHEMAS / name
    if path.parent != SCHEMAS or not path.is_file():
        raise ValueError("Unknown bundled schema: " + name)
    return Draft202012Validator({"$ref": path.as_uri() + fragment},
                               registry=registry(), format_checker=FORMATS)


def validate(value, name, fragment=""):
    try:
        validator(name, fragment).validate(value)
    except ValidationError as error:
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        raise ValueError(f"{name}{location}: {error.message}") from None
    return value
