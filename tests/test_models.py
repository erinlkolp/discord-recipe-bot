from datetime import date
from recipebot.db.models import Guild, Recipe, Ingredient, Instruction, Tag, MealPlan, MealPlanEntry, ShoppingList, ShoppingListItem


def test_create_guild(session):
    guild = Guild(guild_id="111", name="Test Server")
    session.add(guild)
    session.commit()
    result = session.get(Guild, "111")
    assert result.name == "Test Server"


def test_create_recipe(session):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    assert recipe.id is not None
    assert recipe.name == "Pasta"


def test_recipe_cascade_deletes_ingredients(session):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    ing = Ingredient(recipe_id=recipe.id, name="flour", category="pantry")
    session.add(ing)
    session.commit()
    ing_id = ing.id
    session.delete(recipe)
    session.commit()
    assert session.get(Ingredient, ing_id) is None


def test_meal_plan_unique_constraint(session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    mp1 = MealPlan(guild_id="111", week_start_date=date(2026, 3, 16))
    mp2 = MealPlan(guild_id="111", week_start_date=date(2026, 3, 16))
    session.add(mp1)
    session.commit()
    session.add(mp2)
    with pytest.raises(IntegrityError):
        session.commit()
