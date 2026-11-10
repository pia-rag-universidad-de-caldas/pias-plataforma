from typing import Any

def collect_strings(data: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(data, str):
        strings.append(data)
    elif isinstance(data, dict):
        for value in data.values():
            strings.extend(collect_strings(value))
    elif isinstance(data, list):
        for item in data:
            strings.extend(collect_strings(item))
    return strings

def calculate_metrics(data: Any) -> dict[str, int]:
    strings = collect_strings(data)
    non_empty = [value for value in strings if value.strip()]
    return {
        "total_string_values": len(strings),
        "non_empty_string_values": len(non_empty),
        "empty_string_values": len(strings) - len(non_empty),
        "total_characters": sum(len(text) for text in strings),
        "total_words": len(" ".join(strings).split()),
        "total_lines": len(" ".join(strings).splitlines()),
        "unique_string_values": len(set(non_empty)),
        "duplicate_string_values": len(non_empty) - len(set(non_empty))
    }