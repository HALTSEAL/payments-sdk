"""Validate the published input schema without third-party dependencies.

Only schema keywords used by workflow-evaluation.schema.json are accepted. This
is not a general JSON Schema validator. Unknown keywords fail closed.
"""
import json
import re
from pathlib import Path

KEYWORDS = {"$schema", "$id", "title", "type", "additionalProperties", "required", "properties",
            "const", "enum", "minLength", "maxLength", "pattern", "minItems", "maxItems", "items", "prefixItems"}


def validate(value, schema, path="$", *, depth=0):
    if depth > 20 or set(schema) - KEYWORDS:
        raise ValueError("Unsupported evaluation schema")
    if "const" in schema and value != schema["const"]:
        raise ValueError(path+": unexpected value")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(path+": unsupported value")
    kind = schema.get("type")
    if kind and not ((kind == "object" and type(value) is dict) or
                     (kind == "array" and type(value) is list) or
                     (kind == "string" and type(value) is str)):
        raise ValueError(path+": wrong type")
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 10000):
            raise ValueError(path+": text length outside contract")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ValueError(path+": invalid stable reference")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if set(schema.get("required", [])) - set(value):
            raise ValueError(path+": required field missing")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(path+": unrecognized field")
        for key, sub in properties.items():
            if key in value:
                validate(value[key], sub, path+"."+key, depth=depth+1)
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10000):
            raise ValueError(path+": wrong number of paths or exclusions")
        for i, item in enumerate(value):
            if "items" in schema:
                validate(item, schema["items"], path+"["+str(i)+"]", depth=depth+1)
            if i < len(schema.get("prefixItems", [])):
                validate(item, schema["prefixItems"][i], path+"["+str(i)+"]", depth=depth+1)
    return value


def load_workflow(path, schema_path=None):
    path = Path(path)
    if path.stat().st_size > 32768:
        raise ValueError("Workflow input exceeds 32 KiB")
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate workflow JSON key")
            result[key] = value
        return result
    value = json.loads(path.read_text(), object_pairs_hook=unique)
    schema_path = schema_path or Path(__file__).resolve().parents[3] / "schemas/workflow-evaluation.schema.json"
    return validate(value, json.loads(Path(schema_path).read_text()))
