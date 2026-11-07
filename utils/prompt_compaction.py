"""Bound nested lesson/source data before adding it to an LLM review prompt."""
import json


def compact_json(value, *, string_limit=480, item_limit=6, key_limit=32):
    def compact(item):
        if isinstance(item, str):
            if len(item) <= string_limit:
                return item
            return item[:string_limit] + " [truncated]"
        if isinstance(item, dict):
            return {
                key: compact(child)
                for index, (key, child) in enumerate(item.items())
                if index < key_limit
            }
        if isinstance(item, (list, tuple)):
            return [compact(child) for child in item[:item_limit]]
        return item

    return json.dumps(compact(value), ensure_ascii=False, separators=(",", ":"))
