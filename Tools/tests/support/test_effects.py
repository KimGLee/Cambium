"""Source-adjacent execution-effect annotations for Test Catalog.

Use only when a test crosses into a production function that owns the actual
process, temporary-resource, or copy call.  Direct test and fixture call sites
are discovered without annotations.
"""


_EFFECT_KEYS = frozenset((
    "process_calls",
    "temp_resources",
    "file_copies",
    "full_repository_copies",
))


def catalog_effects(**effects):
    """Attach statically parsed effect counts without wrapping the test."""
    if (not effects or set(effects) - _EFFECT_KEYS or
            any(type(value) is not int or value < 0
                for value in effects.values()) or
            not any(effects.values())):
        raise ValueError("catalog effects must be positive known counts")

    def decorate(function):
        function.__catalog_effects__ = dict(effects)
        return function

    return decorate


__all__ = ("catalog_effects",)
