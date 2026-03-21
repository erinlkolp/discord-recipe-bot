import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from recipebot.db.models import Guild, Recipe, Ingredient, Instruction, Tag
from recipebot.cogs.recipes import RecipesCog, AddRecipeModal, EditRecipeModal, SearchPaginationView


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

    from tests.conftest import make_session_factory
    modal = AddRecipeModal(make_session_factory(session))
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

    from tests.conftest import make_session_factory
    modal = AddRecipeModal(make_session_factory(session))
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


@pytest.mark.asyncio
async def test_view_recipe_sends_embed(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    from datetime import timezone
    recipe = Recipe(guild_id="111", name="Pasta", servings=4,
                    created_at=datetime.now(timezone.utc))
    session.add(recipe)
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = RecipesCog(bot)
    await cog.view.callback(cog, mock_interaction, "Pasta")
    mock_interaction.response.send_message.assert_called_once()
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert "embed" in call_kwargs


@pytest.mark.asyncio
async def test_view_recipe_not_found(session, bot, mock_interaction):
    mock_interaction.guild_id = "111"
    cog = RecipesCog(bot)
    await cog.view.callback(cog, mock_interaction, "Ghost Recipe")
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_search_by_name_returns_embed(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    session.add(Recipe(guild_id="111", name="Pasta", servings=4))
    session.commit()
    mock_interaction.guild_id = "111"
    cog = RecipesCog(bot)
    await cog.search.callback(cog, mock_interaction, by="name", query="pasta")
    mock_interaction.response.send_message.assert_called_once()
    _, kwargs = mock_interaction.response.send_message.call_args
    assert "embed" in kwargs


@pytest.mark.asyncio
async def test_search_no_results_ephemeral(session, bot, mock_interaction):
    mock_interaction.guild_id = "111"
    cog = RecipesCog(bot)
    await cog.search.callback(cog, mock_interaction, by="name", query="nonexistent")
    _, kwargs = mock_interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True


def test_search_pagination_view_pages():
    results = [{"name": f"Recipe {i}", "description": None} for i in range(7)]
    view = SearchPaginationView(results)
    embed = view.current_embed()
    assert "1/2" in embed.title
    assert len(embed.fields) == 5

    view._page = 1
    embed2 = view.current_embed()
    assert "2/2" in embed2.title
    assert len(embed2.fields) == 2


@pytest.mark.asyncio
async def test_ingredients_command_replaces(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    from datetime import timezone
    recipe = Recipe(guild_id="111", name="Pasta", servings=4,
                    created_at=datetime.now(timezone.utc))
    session.add(recipe)
    session.commit()
    old_ing = Ingredient(recipe_id=recipe.id, name="old", category="other")
    session.add(old_ing)
    session.commit()

    from recipebot.cogs.recipes import IngredientsModal
    from tests.conftest import make_session_factory
    modal = IngredientsModal(make_session_factory(session), recipe.id)
    modal.ingredients_text.default = "flour, 2, cup, pantry\nsalt, 1, tsp, pantry"
    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    remaining = session.query(Ingredient).filter_by(recipe_id=recipe.id).all()
    assert len(remaining) == 2
    assert remaining[0].name == "flour"


@pytest.mark.asyncio
async def test_ingredients_command_rejects_bad_lines(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    from datetime import timezone
    recipe = Recipe(guild_id="111", name="Pasta", servings=4,
                    created_at=datetime.now(timezone.utc))
    session.add(recipe)
    session.commit()

    from recipebot.cogs.recipes import IngredientsModal
    from tests.conftest import make_session_factory
    modal = IngredientsModal(make_session_factory(session), recipe.id)
    modal.ingredients_text.default = "flour, 2, cup"  # missing category
    await modal.on_submit(mock_interaction)

    mock_interaction.response.send_message.assert_called_once()
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True
    remaining = session.query(Ingredient).filter_by(recipe_id=recipe.id).all()
    assert len(remaining) == 0  # no partial writes
