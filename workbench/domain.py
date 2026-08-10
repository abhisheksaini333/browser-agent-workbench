import hashlib
import json
import re

KINDS = {"purchase", "reservation", "inventory"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_arguments(kind, arguments):
    if kind not in KINDS or not isinstance(arguments, dict):
        raise ValueError("unsupported action")
    fields = {"sku", "quantity"}
    if set(arguments) != fields:
        raise ValueError("exact sku and quantity are required")
    sku, quantity = arguments["sku"], arguments["quantity"]
    if not isinstance(sku, str) or not re.fullmatch(r"[A-Z][A-Z0-9-]{0,31}", sku):
        raise ValueError("invalid sku")
    if type(quantity) is not int or not 1 <= quantity <= 100:
        raise ValueError("quantity must be an integer from 1 to 100")
    return dict(arguments)
