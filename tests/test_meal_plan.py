import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from recipebot.db.models import Guild, Recipe, MealPlan, MealPlanEntry
from recipebot.cogs.meal_plan import MealPlanCog


@pytest.fixture
def bot(session):
    from tests.conftest import make_session_factory
    b = MagicMock()
    b.session_factory = make_session_factory(session)
    return b


@pytest.mark.asyncio
async def test_plan_add_creates_entry(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"

    cog = MealPlanCog(bot)
    with patch("recipebot.cogs.meal_plan.current_week_start", return_value=date(2026, 3, 16)):
        await cog.plan_add.callback(cog, mock_interaction, "Pasta", "monday", "dinner", 2)

    entry = session.query(MealPlanEntry).first()
    assert entry is not None
    assert entry.servings == 2
    assert entry.day_of_week == "monday"


@pytest.mark.asyncio
async def test_plan_add_rejects_duplicate(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    mp = MealPlan(guild_id="111", week_start_date=date(2026, 3, 16))
    session.add(mp)
    session.commit()
    entry = MealPlanEntry(meal_plan_id=mp.id, recipe_id=recipe.id,
                          day_of_week="monday", meal_type="dinner", servings=2)
    session.add(entry)
    session.commit()

    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"
    cog = MealPlanCog(bot)
    with patch("recipebot.cogs.meal_plan.current_week_start", return_value=date(2026, 3, 16)):
        await cog.plan_add.callback(cog, mock_interaction, "Pasta", "monday", "dinner", 2)

    msg_kwargs = mock_interaction.response.send_message.call_args[1]
    assert msg_kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_plan_add_rejects_missing_recipe(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"
    cog = MealPlanCog(bot)
    with patch("recipebot.cogs.meal_plan.current_week_start", return_value=date(2026, 3, 16)):
        await cog.plan_add.callback(cog, mock_interaction, "Nonexistent", "monday", "dinner", 2)
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True
    embed = kwargs.get("embed")
    assert "not found" in embed.description.lower()


@pytest.mark.asyncio
async def test_plan_add_missing_recipe_skips_guild_upsert(session, bot, mock_interaction):
    """upsert_guild should not run when the recipe doesn't exist."""
    mock_interaction.guild_id = "222"
    mock_interaction.guild.name = "New Guild"
    mock_interaction.user.id = "999"
    cog = MealPlanCog(bot)
    with patch("recipebot.cogs.meal_plan.current_week_start", return_value=date(2026, 3, 16)):
        await cog.plan_add.callback(cog, mock_interaction, "Nonexistent", "monday", "dinner", 2)
    assert session.query(Guild).filter_by(guild_id="222").first() is None
