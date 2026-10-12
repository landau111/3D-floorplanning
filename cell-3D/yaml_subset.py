"""Dependency-free YAML subset, shared from folding_dse/optimize.py."""
import json
import re

def _scalar(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        contents = value[1:-1].strip()
        return [_scalar(part) for part in _flow_parts(contents)] if contents else []
    if value.startswith("{") and value.endswith("}"):
        result = {}
        for part in _flow_parts(value[1:-1]):
            key, val = part.split(":", 1)
            key = key.strip().strip("\"'")
            if key in result:
                raise ValueError("Duplicate YAML key: " + key)
            result[key] = _scalar(val)
        return result
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return json.loads(value) if value[0] == '"' else value[1:-1].replace("''", "'")
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
        return float(value)
    if value in ("true", "false"):
        return value == "true"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value):
        raise ValueError(f"Unsupported YAML scalar in compact configuration: {value!r}")
    return value

def _flow_parts(value):
    parts, depth, quote, start = [], 0, None, 0
    for i, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:i]); start = i + 1
    if value[start:].strip():
        parts.append(value[start:])
    return parts

def _parse_compact_yaml(raw: str) -> dict:
    """Strict subset: mappings, indentless lists, list mappings and flow values.

    This is intentionally not a general YAML implementation (no anchors/tags).
    Duplicate keys are errors so a constraint cannot silently disappear.
    """
    lines = []
    for number, source in enumerate(raw.splitlines(), 1):
        if "\t" in source:
            raise ValueError("Line {}: YAML indentation must use spaces".format(number))
        line = source.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        lines.append((len(line) - len(line.lstrip()), line.strip(), number))

    def entry(text, number):
        if ":" not in text:
            raise ValueError("Line {}: expected key: value".format(number))
        key, val = text.split(":", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Line {}: invalid key {}".format(number, key))
        return key, val.strip()

    def block(index, indent, is_list=False):
        result = [] if is_list else {}
        while index < len(lines) and lines[index][0] == indent:
            _, content, number = lines[index]
            if content.startswith("- ") != is_list:
                break
            index += 1
            if is_list:
                content = content[2:]
                if ":" not in content or content[0] in "[{\"'":
                    result.append(_scalar(content)); continue
                key, val = entry(content, number)
                if not val:
                    raise ValueError("Line {}: empty list mapping value".format(number))
                item = {key: _scalar(val)}
                if index < len(lines) and lines[index][0] > indent:
                    if lines[index][0] != indent + 2:
                        raise ValueError("Line {}: list fields require {} spaces".format(lines[index][2], indent + 2))
                    more, index = block(index, indent + 2)
                    if set(more) & set(item):
                        raise ValueError("Duplicate list mapping field")
                    item.update(more)
                result.append(item)
            else:
                key, val = entry(content, number)
                if key in result:
                    raise ValueError("Line {}: duplicate key {}".format(number, key))
                if val:
                    result[key] = _scalar(val)
                elif index < len(lines) and (lines[index][0] > indent or
                        (lines[index][0] == indent and lines[index][1].startswith("- "))):
                    result[key], index = block(index, lines[index][0], lines[index][1].startswith("- "))
                else:
                    result[key] = []
        return result, index

    if not lines:
        raise ValueError("Empty configuration")
    data, end = block(0, 0)
    if end != len(lines):
        raise ValueError("Line {}: unexpected indentation".format(lines[end][2]))
    return data
