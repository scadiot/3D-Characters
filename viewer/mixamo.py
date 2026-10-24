"""Convention de nommage des bones Mixamo."""
import re

_PREFIX = re.compile(r"^mixamorig\d*[:_]")


def normalize(name: str) -> str:
    return _PREFIX.sub("", name)
