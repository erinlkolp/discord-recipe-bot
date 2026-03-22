from decimal import Decimal
from recipebot.parsers import parse_ingredients, parse_instructions, aggregate_shopping_items


def test_parse_ingredients_valid():
    text = "flour, 2, cup, pantry\nsalt, 1, tsp, pantry"
    items, errors = parse_ingredients(text)
    assert len(errors) == 0
    assert len(items) == 2
    assert items[0].name == "flour"
    assert items[0].quantity == Decimal("2")
    assert items[0].unit == "cup"
    assert items[0].category == "pantry"


def test_parse_ingredients_case_insensitive_category():
    text = "milk, 1, cup, DAIRY"
    items, errors = parse_ingredients(text)
    assert len(errors) == 0
    assert items[0].category == "dairy"


def test_parse_ingredients_wrong_field_count():
    text = "flour, 2, cup"
    items, errors = parse_ingredients(text)
    assert len(items) == 0
    assert len(errors) == 1
    assert errors[0].line_number == 1


def test_parse_ingredients_invalid_quantity():
    text = "flour, abc, cup, pantry"
    items, errors = parse_ingredients(text)
    assert len(errors) == 1
    assert "abc" in errors[0].reason


def test_parse_ingredients_invalid_category():
    text = "flour, 2, cup, snacks"
    items, errors = parse_ingredients(text)
    assert len(errors) == 1
    assert "snacks" in errors[0].reason


def test_parse_ingredients_skips_blank_lines():
    text = "flour, 2, cup, pantry\n\nsalt, 1, tsp, pantry"
    items, errors = parse_ingredients(text)
    assert len(items) == 2
    assert len(errors) == 0


def test_parse_instructions_basic():
    steps = parse_instructions("Boil water\nAdd pasta\nDrain")
    assert steps == ["Boil water", "Add pasta", "Drain"]


def test_parse_instructions_skips_blanks():
    steps = parse_instructions("Step one\n\nStep two")
    assert steps == ["Step one", "Step two"]


def test_aggregate_shopping_items_sums_same_unit():
    items = [
        {"name": "flour", "quantity": Decimal("2"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
        {"name": "flour", "quantity": Decimal("1"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert len(result) == 1
    assert result[0]["total_quantity"] == Decimal("3")


def test_aggregate_shopping_items_scales_by_servings():
    items = [
        {"name": "flour", "quantity": Decimal("2"), "unit": "cup", "category": "pantry",
         "entry_servings": 8, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert result[0]["total_quantity"] == Decimal("4")


def test_aggregate_shopping_items_different_units_separate():
    items = [
        {"name": "flour", "quantity": Decimal("2"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
        {"name": "flour", "quantity": Decimal("100"), "unit": "g", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert len(result) == 2


def test_aggregate_shopping_items_null_quantity_included():
    items = [
        {"name": "salt", "quantity": None, "unit": "to taste", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert len(result) == 1
    assert result[0]["ingredient_name"] == "salt"
    assert result[0]["total_quantity"] is None


def test_aggregate_shopping_items_preserves_original_casing():
    items = [
        {"name": "All-Purpose Flour", "quantity": Decimal("2"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
        {"name": "all-purpose flour", "quantity": Decimal("1"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert len(result) == 1
    assert result[0]["ingredient_name"] == "All-Purpose Flour"  # first-seen casing preserved
    assert result[0]["total_quantity"] == Decimal("3")
