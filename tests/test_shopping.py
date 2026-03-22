import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from recipebot.db.models import Guild, Recipe, Ingredient, MealPlan, MealPlanEntry, ShoppingList, ShoppingListItem
from recipebot.cogs.shopping import ShoppingCog


@pytest.fixture
def bot(session):
    from tests.conftest import make_session_factory
    b = MagicMock()
    b.session_factory = make_session_factory(session)
    return b


def _seed_plan_with_recipe(session, guild_id="111"):
    session.add(Guild(guild_id=guild_id, name="Test"))
    session.commit()
    recipe = Recipe(guild_id=guild_id, name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    session.add(Ingredient(recipe_id=recipe.id, name="flour", quantity=Decimal("2"),
                           unit="cup", category="pantry"))
    session.commit()
    mp = MealPlan(guild_id=guild_id, week_start_date=date(2026, 3, 16))
    session.add(mp)
    session.commit()
    session.add(MealPlanEntry(meal_plan_id=mp.id, recipe_id=recipe.id,
                              day_of_week="monday", meal_type="dinner", servings=4))
    session.commit()
    return mp


@pytest.mark.asyncio
async def test_shopping_generate_creates_list(session, bot, mock_interaction):
    mp = _seed_plan_with_recipe(session)
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_generate.callback(cog, mock_interaction)
    sl = session.query(ShoppingList).filter_by(guild_id="111").first()
    assert sl is not None
    assert len(sl.items) == 1
    assert sl.items[0].ingredient_name == "flour"
    assert sl.items[0].total_quantity == Decimal("2.000")


@pytest.mark.asyncio
async def test_shopping_generate_replaces_existing(session, bot, mock_interaction):
    mp = _seed_plan_with_recipe(session)
    old_sl = ShoppingList(guild_id="111", meal_plan_id=mp.id,
                          generated_at=datetime.now(timezone.utc))
    session.add(old_sl)
    session.commit()
    old_id = old_sl.id
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_generate.callback(cog, mock_interaction)
    assert session.get(ShoppingList, old_id) is None
    assert session.query(ShoppingList).filter_by(guild_id="111").count() == 1


@pytest.mark.asyncio
async def test_shopping_view_no_list(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_view.callback(cog, mock_interaction)
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_shopping_generate_no_meal_plan(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_generate.callback(cog, mock_interaction)
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_shopping_generate_no_meal_plan_skips_guild_upsert(session, bot, mock_interaction):
    """upsert_guild should not run (and leave uncommitted state) when there's no meal plan."""
    mock_interaction.guild_id = "222"
    mock_interaction.guild.name = "New Guild"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_generate.callback(cog, mock_interaction)
    # Guild row should NOT have been persisted on the early-return path
    assert session.query(Guild).filter_by(guild_id="222").first() is None
