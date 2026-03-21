from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from typing import Optional

VALID_CATEGORIES = {'produce', 'dairy', 'meat', 'seafood', 'pantry', 'frozen', 'bakery', 'other'}


@dataclass
class ParsedIngredient:
    name: str
    quantity: Optional[Decimal]
    unit: str
    category: str


@dataclass
class ParseError:
    line_number: int
    line: str
    reason: str


def parse_ingredients(text: str) -> tuple[list[ParsedIngredient], list[ParseError]]:
    """Parse ingredient text. Format per line: name, quantity, unit, category.
    Blank lines are silently skipped. Returns (ingredients, errors).
    On any error the whole submission should be rejected — errors list will be non-empty."""
    ingredients: list[ParsedIngredient] = []
    errors: list[ParseError] = []
    for i, raw_line in enumerate(text.strip().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 4:
            errors.append(ParseError(i, raw_line,
                f"Expected 4 comma-separated fields, got {len(parts)}"))
            continue
        name, qty_str, unit, cat_str = parts
        if not name:
            errors.append(ParseError(i, raw_line, "Name cannot be empty"))
            continue
        category = cat_str.lower()
        if category not in VALID_CATEGORIES:
            errors.append(ParseError(i, raw_line,
                f"Invalid category '{cat_str}'. Valid values: {', '.join(sorted(VALID_CATEGORIES))}"))
            continue
        try:
            quantity = Decimal(qty_str) if qty_str else None
        except InvalidOperation:
            errors.append(ParseError(i, raw_line, f"Invalid quantity '{qty_str}' — must be a number"))
            continue
        ingredients.append(ParsedIngredient(name=name, quantity=quantity, unit=unit, category=category))
    return ingredients, errors


def parse_instructions(text: str) -> list[str]:
    """Parse instruction text. One step per line, blank lines skipped.
    Returned list index + 1 = step_number."""
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def aggregate_shopping_items(items: list[dict]) -> list[dict]:
    """Aggregate and scale ingredient quantities for a shopping list.

    Each item dict must have keys:
        name, quantity (Decimal|None), unit, category,
        entry_servings (int), recipe_servings (int)

    Returns list of dicts with keys: ingredient_name, total_quantity, unit, category.
    Items with the same (name.lower(), unit) are summed after scaling.
    Different units for the same ingredient produce separate line items.
    """
    totals: dict[tuple, Decimal] = defaultdict(Decimal)
    categories: dict[tuple, str] = {}

    seen_keys: set = set()
    for item in items:
        scale = Decimal(str(item['entry_servings'])) / Decimal(str(item['recipe_servings']))
        key = (item['name'].lower(), item['unit'] or '')
        seen_keys.add(key)
        if item['quantity'] is not None:
            totals[key] += item['quantity'] * scale
        categories[key] = item['category']

    return [
        {
            'ingredient_name': key[0],
            'unit': key[1],
            'total_quantity': totals[key] if totals[key] else None,
            'category': categories[key],
        }
        for key in seen_keys
    ]
