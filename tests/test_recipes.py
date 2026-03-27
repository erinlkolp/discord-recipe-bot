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


@pytest.mark.asyncio
async def test_delete_missing_recipe_skips_guild_upsert(session, bot, mock_interaction):
    """delete should not call upsert_guild — it doesn't write guild-FK-dependent data."""
    mock_interaction.guild_id = "222"
    mock_interaction.guild.name = "New Guild"
    cog = RecipesCog(bot)
    await cog.delete.callback(cog, mock_interaction, "Nonexistent")
    assert session.query(Guild).filter_by(guild_id="222").first() is None


@pytest.mark.asyncio
async def test_edit_modal_missing_recipe_skips_guild_upsert(session, bot, mock_interaction):
    """EditRecipeModal should not call upsert_guild — the recipe's guild already exists."""
    mock_interaction.guild_id = "222"
    mock_interaction.guild.name = "New Guild"
    mock_interaction.user.id = "999"
    from tests.conftest import make_session_factory
    modal = EditRecipeModal(make_session_factory(session), recipe_id=9999,
                            recipe_name="Ghost", recipe_description="",
                            recipe_servings=4, recipe_prep_time=None, recipe_cook_time=None)
    modal.name.default = "Ghost"
    modal.servings.default = "4"
    modal.description.default = ""
    modal.prep_time.default = ""
    modal.cook_time.default = ""
    await modal.on_submit(mock_interaction)
    assert session.query(Guild).filter_by(guild_id="222").first() is None


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
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Line 1" in embed.description
    remaining = session.query(Ingredient).filter_by(recipe_id=recipe.id).all()
    assert len(remaining) == 0  # no partial writes


@pytest.mark.asyncio
async def test_instructions_modal_replaces(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    from datetime import timezone
    recipe = Recipe(guild_id="111", name="Pasta", servings=4,
                    created_at=datetime.now(timezone.utc))
    session.add(recipe)
    session.commit()
    old_inst = Instruction(recipe_id=recipe.id, step_number=1, instruction_text="old step")
    session.add(old_inst)
    session.commit()

    from recipebot.cogs.recipes import InstructionsModal
    from tests.conftest import make_session_factory
    modal = InstructionsModal(make_session_factory(session), recipe.id)
    modal.instructions_text.default = "Boil water\nAdd pasta\nDrain"
    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    remaining = session.query(Instruction).filter_by(recipe_id=recipe.id).order_by(Instruction.step_number).all()
    assert len(remaining) == 3
    assert remaining[0].instruction_text == "Boil water"
    assert remaining[0].step_number == 1
    assert remaining[2].step_number == 3


@pytest.mark.asyncio
async def test_instructions_modal_empty_rejects(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    from datetime import timezone
    recipe = Recipe(guild_id="111", name="Pasta", servings=4,
                    created_at=datetime.now(timezone.utc))
    session.add(recipe)
    session.commit()

    from recipebot.cogs.recipes import InstructionsModal
    from tests.conftest import make_session_factory
    modal = InstructionsModal(make_session_factory(session), recipe.id)
    modal.instructions_text.default = "\n\n\n"  # all blank lines
    await modal.on_submit(mock_interaction)

    mock_interaction.response.send_message.assert_called_once()
    _, kwargs = mock_interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_tag_modal_replaces(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    from datetime import timezone
    recipe = Recipe(guild_id="111", name="Pasta", servings=4,
                    created_at=datetime.now(timezone.utc))
    session.add(recipe)
    session.commit()
    old_tag = Tag(recipe_id=recipe.id, tag_name="old")
    session.add(old_tag)
    session.commit()

    from recipebot.cogs.recipes import TagModal
    from tests.conftest import make_session_factory
    modal = TagModal(make_session_factory(session), recipe.id, "old")
    modal.tags_text.default = "italian, pasta"
    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    remaining = session.query(Tag).filter_by(recipe_id=recipe.id).all()
    tag_names = {t.tag_name for t in remaining}
    assert tag_names == {"italian", "pasta"}


@pytest.mark.asyncio
async def test_wizard_view_finalize_creates_complete_recipe(session, bot, mock_interaction):
    """Wizard finalize should create recipe + ingredients + instructions in one transaction."""
    from recipebot.cogs.recipes import AddRecipeWizardView
    from recipebot.parsers import ParsedIngredient
    from decimal import Decimal

    session.add(Guild(guild_id="111", name="Test"))
    session.commit()

    view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    view.metadata = {
        "name": "Spaghetti",
        "description": "Classic pasta",
        "servings": 4,
        "prep_time": 10,
        "cook_time": 20,
    }
    view.ingredients = [
        ParsedIngredient(name="pasta", quantity=Decimal("200"), unit="g", category="pantry"),
        ParsedIngredient(name="sauce", quantity=Decimal("1"), unit="cup", category="pantry"),
    ]
    view.instructions = ["Boil water", "Cook pasta", "Add sauce"]

    mock_interaction.guild_id = "111"
    await view.finalize(mock_interaction)

    recipe = session.query(Recipe).filter_by(guild_id="111", name="Spaghetti").first()
    assert recipe is not None
    assert recipe.servings == 4
    assert recipe.prep_time == 10
    assert recipe.cook_time == 20
    assert recipe.created_by == "999"
    assert len(recipe.ingredients) == 2
    assert len(recipe.instructions) == 3
    assert recipe.instructions[0].instruction_text == "Boil water"
    assert recipe.instructions[0].step_number == 1

    # Final message should be a public embed (no ephemeral kwarg)
    mock_interaction.response.send_message.assert_called_once()
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert "embed" in call_kwargs
    assert call_kwargs.get("ephemeral") is not True


@pytest.mark.asyncio
async def test_wizard_modal_stores_metadata_and_sends_button(session, bot, mock_interaction):
    """Modal 1 should validate, store metadata on the view, and send an ephemeral message with a view."""
    from recipebot.cogs.recipes import AddRecipeWizardModal, AddRecipeWizardView

    wizard_view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    modal = AddRecipeWizardModal(wizard_view)
    modal.name.default = "Spaghetti"
    modal.description.default = "Classic pasta"
    modal.servings.default = "4"
    modal.prep_time.default = "10"
    modal.cook_time.default = "20"

    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    # Metadata should be stored on the view
    assert wizard_view.metadata is not None
    assert wizard_view.metadata["name"] == "Spaghetti"
    assert wizard_view.metadata["servings"] == 4
    assert wizard_view.metadata["prep_time"] == 10

    # Should send ephemeral message with a view (button)
    mock_interaction.response.send_message.assert_called_once()
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert "view" in call_kwargs

    # No recipe in DB yet
    assert session.query(Recipe).count() == 0


@pytest.mark.asyncio
async def test_wizard_modal_invalid_servings_sends_error(session, bot, mock_interaction):
    """Modal 1 with invalid servings should send error and not store metadata."""
    from recipebot.cogs.recipes import AddRecipeWizardModal, AddRecipeWizardView

    wizard_view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    modal = AddRecipeWizardModal(wizard_view)
    modal.name.default = "Bread"
    modal.description.default = ""
    modal.servings.default = "abc"
    modal.prep_time.default = ""
    modal.cook_time.default = ""

    await modal.on_submit(mock_interaction)

    assert wizard_view.metadata is None
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert call_kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_wizard_view_finalize_optional_fields_none(session, bot, mock_interaction):
    """Finalize should handle None description, prep_time, cook_time."""
    from recipebot.cogs.recipes import AddRecipeWizardView
    from recipebot.parsers import ParsedIngredient
    from decimal import Decimal

    session.add(Guild(guild_id="111", name="Test"))
    session.commit()

    view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    view.metadata = {
        "name": "Toast",
        "description": None,
        "servings": 1,
        "prep_time": None,
        "cook_time": None,
    }
    view.ingredients = [
        ParsedIngredient(name="bread", quantity=Decimal("2"), unit="slice", category="bakery"),
    ]
    view.instructions = ["Put bread in toaster"]

    mock_interaction.guild_id = "111"
    await view.finalize(mock_interaction)

    recipe = session.query(Recipe).filter_by(guild_id="111", name="Toast").first()
    assert recipe is not None
    assert recipe.description is None
    assert recipe.prep_time is None
    assert recipe.cook_time is None


@pytest.mark.asyncio
async def test_wizard_ingredients_modal_stores_and_sends_button(session, bot, mock_interaction):
    """Modal 2 should parse ingredients, store on view, and send next button."""
    from recipebot.cogs.recipes import WizardIngredientsModal, AddRecipeWizardView

    wizard_view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    modal = WizardIngredientsModal(wizard_view)
    modal.ingredients_text.default = "flour, 2, cup, pantry\neggs, 3, , dairy"

    await modal.on_submit(mock_interaction)

    assert wizard_view.ingredients is not None
    assert len(wizard_view.ingredients) == 2
    assert wizard_view.ingredients[0].name == "flour"

    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert "view" in call_kwargs

    # Still no recipe in DB
    assert session.query(Recipe).count() == 0


@pytest.mark.asyncio
async def test_wizard_ingredients_modal_parse_error(session, bot, mock_interaction):
    """Modal 2 with bad format should send error and not store ingredients."""
    from recipebot.cogs.recipes import WizardIngredientsModal, AddRecipeWizardView

    wizard_view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    modal = WizardIngredientsModal(wizard_view)
    modal.ingredients_text.default = "flour, 2, cup"  # missing category

    await modal.on_submit(mock_interaction)

    assert wizard_view.ingredients is None
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert "Line 1" in call_kwargs["embed"].description


@pytest.mark.asyncio
async def test_wizard_instructions_modal_triggers_finalize(session, bot, mock_interaction):
    """Modal 3 should parse instructions and call finalize, creating the full recipe."""
    from recipebot.cogs.recipes import WizardInstructionsModal, AddRecipeWizardView
    from recipebot.parsers import ParsedIngredient
    from decimal import Decimal

    session.add(Guild(guild_id="111", name="Test"))
    session.commit()

    wizard_view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    wizard_view.metadata = {
        "name": "Pasta",
        "description": "Quick dinner",
        "servings": 2,
        "prep_time": 5,
        "cook_time": 10,
    }
    wizard_view.ingredients = [
        ParsedIngredient(name="pasta", quantity=Decimal("200"), unit="g", category="pantry"),
    ]

    modal = WizardInstructionsModal(wizard_view)
    modal.instructions_text.default = "Boil water\nCook pasta\nDrain"

    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    # Recipe should now exist in DB with everything
    recipe = session.query(Recipe).filter_by(guild_id="111", name="Pasta").first()
    assert recipe is not None
    assert len(recipe.ingredients) == 1
    assert len(recipe.instructions) == 3

    # Public embed sent (not ephemeral)
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert "embed" in call_kwargs
    assert call_kwargs.get("ephemeral") is not True


@pytest.mark.asyncio
async def test_wizard_instructions_modal_empty_rejects(session, bot, mock_interaction):
    """Modal 3 with blank input should send error and not finalize."""
    from recipebot.cogs.recipes import WizardInstructionsModal, AddRecipeWizardView

    wizard_view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    modal = WizardInstructionsModal(wizard_view)
    modal.instructions_text.default = "\n\n\n"

    await modal.on_submit(mock_interaction)

    assert wizard_view.instructions is None
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert call_kwargs.get("ephemeral") is True
    assert session.query(Recipe).count() == 0


@pytest.mark.asyncio
async def test_add_command_sends_wizard_modal(session, bot, mock_interaction):
    """The /recipebot add command should now send AddRecipeWizardModal."""
    from recipebot.cogs.recipes import AddRecipeWizardModal

    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"

    cog = RecipesCog(bot)
    await cog.add.callback(cog, mock_interaction)

    mock_interaction.response.send_modal.assert_called_once()
    modal = mock_interaction.response.send_modal.call_args[0][0]
    assert isinstance(modal, AddRecipeWizardModal)


@pytest.mark.asyncio
async def test_wizard_full_flow_end_to_end(session, bot, mock_interaction):
    """Simulate the complete 3-modal wizard flow from /recipebot add to final save."""
    from recipebot.cogs.recipes import AddRecipeWizardModal, AddRecipeWizardView

    session.add(Guild(guild_id="111", name="Test"))
    session.commit()

    # Step 1: Create wizard view and modal 1 (as the add command would)
    wizard_view = AddRecipeWizardView(
        session_factory=bot.session_factory,
        guild_id="111",
        guild_name="Test",
        user_id="999",
    )
    modal1 = AddRecipeWizardModal(wizard_view)
    modal1.name.default = "Tacos"
    modal1.description.default = "Tuesday tacos"
    modal1.servings.default = "4"
    modal1.prep_time.default = "15"
    modal1.cook_time.default = "10"

    interaction1 = MagicMock()
    interaction1.guild_id = "111"
    interaction1.response.send_message = AsyncMock()
    await modal1.on_submit(interaction1)

    # Verify step 1 complete, metadata stored
    assert wizard_view.metadata is not None
    assert wizard_view.metadata["name"] == "Tacos"
    assert session.query(Recipe).count() == 0  # nothing saved yet

    # Step 2: Simulate button click opening modal 2
    # Get the button view that was sent
    button_view_1 = interaction1.response.send_message.call_args[1]["view"]
    interaction2 = MagicMock()
    interaction2.response.send_modal = AsyncMock()
    interaction2.response.send_message = AsyncMock()
    # Click the button (callback is already bound to the view)
    await button_view_1.open_ingredients.callback(interaction2)
    modal2 = interaction2.response.send_modal.call_args[0][0]

    modal2.ingredients_text.default = "beef, 1, lb, meat\ntortillas, 8, , bakery\ncheese, 1, cup, dairy"
    interaction2b = MagicMock()
    interaction2b.guild_id = "111"
    interaction2b.response.send_message = AsyncMock()
    await modal2.on_submit(interaction2b)

    assert wizard_view.ingredients is not None
    assert len(wizard_view.ingredients) == 3
    assert session.query(Recipe).count() == 0  # still nothing saved

    # Step 3: Simulate button click opening modal 3
    button_view_2 = interaction2b.response.send_message.call_args[1]["view"]
    interaction3 = MagicMock()
    interaction3.response.send_modal = AsyncMock()
    interaction3.response.send_message = AsyncMock()
    await button_view_2.open_instructions.callback(interaction3)
    modal3 = interaction3.response.send_modal.call_args[0][0]

    modal3.instructions_text.default = "Brown the beef\nWarm tortillas\nAssemble tacos"
    interaction3b = MagicMock()
    interaction3b.guild_id = "111"
    interaction3b.response.send_message = AsyncMock()
    await modal3.on_submit(interaction3b)

    # Now everything should be saved
    recipe = session.query(Recipe).filter_by(guild_id="111", name="Tacos").first()
    assert recipe is not None
    assert recipe.servings == 4
    assert len(recipe.ingredients) == 3
    assert len(recipe.instructions) == 3
    assert recipe.ingredients[0].name == "beef"
    assert recipe.instructions[0].instruction_text == "Brown the beef"

    # Final message should be a public embed
    call_kwargs = interaction3b.response.send_message.call_args[1]
    assert "embed" in call_kwargs
    assert call_kwargs.get("ephemeral") is not True
