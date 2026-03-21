import pytest
from unittest.mock import AsyncMock, MagicMock
from recipebot.db.models import Guild, Recipe
from recipebot.cogs.recipes import RecipesCog, AddRecipeModal, EditRecipeModal


@pytest.fixture
def bot(session):
    from tests.conftest import make_session_factory
    b = MagicMock()
    b.session_factory = make_session_factory(session)
    return b


@pytest.mark.asyncio
async def test_add_recipe_modal_creates_recipe(session, bot, mock_interaction):
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()

    modal = AddRecipeModal(session)
    modal.name.default = "Spaghetti"
    modal.description.default = "Classic pasta"
    modal.servings.default = "4"
    modal.prep_time.default = "10"
    modal.cook_time.default = "20"

    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    recipe = session.query(Recipe).filter_by(guild_id="111", name="Spaghetti").first()
    assert recipe is not None
    assert recipe.servings == 4


@pytest.mark.asyncio
async def test_delete_recipe_missing(session, bot, mock_interaction):
    cog = RecipesCog(bot)
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    await cog.delete.callback(cog, mock_interaction, "Nonexistent")
    mock_interaction.response.send_message.assert_called_once()
    args, kwargs = mock_interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_add_recipe_modal_invalid_servings(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"

    modal = AddRecipeModal(session)
    modal.servings.default = "abc"
    modal.name.default = "Bread"
    modal.description.default = ""
    modal.prep_time.default = ""
    modal.cook_time.default = ""
    await modal.on_submit(mock_interaction)

    mock_interaction.response.send_message.assert_called_once()
    _, kwargs = mock_interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
    # No recipe should have been created
    from recipebot.db.models import Recipe
    assert session.query(Recipe).count() == 0


@pytest.mark.asyncio
async def test_edit_recipe_missing(session, bot, mock_interaction):
    cog = RecipesCog(bot)
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    await cog.edit.callback(cog, mock_interaction, "Nonexistent")
    mock_interaction.response.send_message.assert_called_once()
    _, kwargs = mock_interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
