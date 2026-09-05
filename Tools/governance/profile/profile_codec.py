"""Tool-owned TOML codec, with no Profile policy or implicit defaults.

The declared decoder dependency is shared by all supported Python versions. Only
ordinary JSON-compatible values cross the CUE boundary; temporal values must
be explicit contract-defined strings, not parser-specific date objects.
Natural-language strings, including line endings, round-trip unchanged.
"""

from collections.abc import Mapping
import math


class ProfileCodecError(ValueError):
    """Input is not a representable Profile document; no values were filled."""


def _plain(value, path=()):
    if isinstance(value, Mapping):
        result = {}
        if any(type(key) is not str for key in value):
            raise ProfileCodecError("Profile keys must be strings at %r" % (path,))
        for key in sorted(value):
            result[key] = _plain(value[key], (*path, key))
        return result
    if isinstance(value, (list, tuple)):
        return [_plain(item, (*path, index)) for index, item in enumerate(value)]
    if type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ProfileCodecError(
        "unsupported Profile value at %r: %s; no null/default is inferred"
        % (path, type(value).__name__))


def loads_profile(data):
    """Decode bytes/text without interpreting policy, selection, or comments."""
    try:
        import tomli
    except ImportError as exc:
        raise ProfileCodecError(
            "Profile TOML decoder unavailable; install Tools/requirements-profile.txt") from exc
    try:
        text = data.decode("utf-8", errors="strict") if isinstance(data, bytes) else data
        if not isinstance(text, str):
            raise ProfileCodecError("Profile source must be UTF-8 bytes or text")
        return _plain(tomli.loads(text))
    except (UnicodeError, tomli.TOMLDecodeError) as exc:
        raise ProfileCodecError("invalid Profile TOML: %s" % exc) from exc


def dumps_profile(document):
    """Deterministically encode plain data and independently parse it back."""
    try:
        import tomli_w
    except ImportError as exc:
        raise ProfileCodecError(
            "Profile TOML encoder unavailable; install Tools/requirements-profile.txt") from exc
    if not isinstance(document, Mapping):
        raise ProfileCodecError("Profile document must be an object")
    plain = _plain(document)
    try:
        encoded = tomli_w.dumps(plain).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ProfileCodecError("cannot encode Profile TOML: %s" % exc) from exc
    if loads_profile(encoded) != plain:
        raise ProfileCodecError("Profile encoding did not preserve its values")
    return encoded
