# Add Recipe Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-command recipe creation flow with a single `/recipebot add` that chains three modals via button prompts, saving everything in one transaction at the end.

**Architecture:** Four new classes in `recipebot/cogs/recipes.py`: `AddRecipeWizardModal` (metadata), `WizardIngredientsModal`, `WizardInstructionsModal`, and `AddRecipeWizardView` (state holder + button views + finalize). The existing `add` command switches to use the wizard. All existing classes stay untouched.

**Tech Stack:** discord.py (modals, views, buttons, embeds), SQLAlchemy ORM, pytest + unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-26-add-recipe-wizard-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `recipebot/cogs/recipes.py` | Modify | Add 4 new classes; rewire `RecipesCog.add` command |
| `tests/test_recipes.py` | Modify | Add wizard tests |

No new files. All changes are additions to existing files.

---

### Task 1: AddRecipeWizardView — state holder and finalize method

The view is the backbone — it holds accumulated data and performs the final DB save. Build and test it first so subsequent tasks can reference it.

**Files:**
- Modify: `recipebot/cogs/recipes.py` (add class after `SearchPaginationView`, before `recipebot_group`)
- Test: `tests/test_recipes.py`

- [ ] **Step 1: Write the failing test for finalize happy path**

```python
# tests/test_recipes.py — add at bottom

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_view_finalize_creates_complete_recipe -v`
Expected: FAIL — `ImportError: cannot import name 'AddRecipeWizardView'`

- [ ] **Step 3: Implement AddRecipeWizardView**

Add this class in `recipebot/cogs/recipes.py` after `SearchPaginationView` and before the `recipebot_group = ...` line:

```python
class AddRecipeWizardView(discord.ui.View):
    """Holds accumulated state across the 3-step add-recipe wizard.

    Each modal stores its validated data here. After all three modals complete,
    finalize() saves everything in one DB transaction.
    """

    def __init__(self, session_factory, guild_id: str, guild_name: str, user_id: str):
        super().__init__(timeout=600)
        self.session_factory = session_factory
        self.guild_id = guild_id
        self.guild_name = guild_name
        self.user_id = user_id
        self.metadata: dict | None = None
        self.ingredients: list | None = None
        self.instructions: list[str] | None = None

    async def finalize(self, interaction: discord.Interaction):
        from recipebot.db.models import Ingredient, Instruction
        m = self.metadata
        with self.session_factory() as session:
            upsert_guild(session, self.guild_id, self.guild_name)
            now = datetime.now(timezone.utc)
            recipe = Recipe(
                guild_id=self.guild_id,
                name=m["name"],
                description=m["description"],
                servings=m["servings"],
                prep_time=m["prep_time"],
                cook_time=m["cook_time"],
                created_by=self.user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(recipe)
            session.flush()
            for item in self.ingredients:
                session.add(Ingredient(
                    recipe_id=recipe.id,
                    name=item.name,
                    quantity=item.quantity,
                    unit=item.unit,
                    category=item.category,
                ))
            for i, step in enumerate(self.instructions, start=1):
                session.add(Instruction(
                    recipe_id=recipe.id,
                    step_number=i,
                    instruction_text=step,
                ))
            session.flush()
            session.refresh(recipe)
            embed = RecipesCog._build_recipe_embed(recipe)
            session.commit()
        self.stop()
        await interaction.response.send_message(embed=embed)
```

Also add the `RecipesCog` import reference — `_build_recipe_embed` is a `@staticmethod`, so `RecipesCog._build_recipe_embed(recipe)` works since `RecipesCog` is defined later in the same file. Since Python resolves names at call time (not definition time), this forward reference is fine at runtime. However, `AddRecipeWizardView` is defined *above* `RecipesCog` in the file. The `finalize` method only calls `RecipesCog._build_recipe_embed` at runtime (when the user completes the wizard), by which point `RecipesCog` is fully defined. No import or reordering needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_view_finalize_creates_complete_recipe -v`
Expected: PASS

- [ ] **Step 5: Write test for finalize with optional fields as None**

```python
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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_view_finalize_optional_fields_none -v`
Expected: PASS (implementation already handles None)

- [ ] **Step 7: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: add AddRecipeWizardView with finalize method

Holds accumulated state from the 3-step wizard and saves recipe +
ingredients + instructions in a single DB transaction."
```

---

### Task 2: AddRecipeWizardModal (Modal 1 — metadata)

Validates metadata fields and stores them on the wizard view. On success, responds with an ephemeral step-complete message plus a view containing a "Next: Add Ingredients" button.

**Files:**
- Modify: `recipebot/cogs/recipes.py` (add class before `AddRecipeWizardView`)
- Test: `tests/test_recipes.py`

- [ ] **Step 1: Write failing test for wizard modal happy path**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_modal_stores_metadata_and_sends_button -v`
Expected: FAIL — `ImportError: cannot import name 'AddRecipeWizardModal'`

- [ ] **Step 3: Write failing test for invalid servings**

```python
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
```

- [ ] **Step 4: Implement AddRecipeWizardModal**

Add in `recipebot/cogs/recipes.py` after `SearchPaginationView` and before `AddRecipeWizardView`:

```python
class _WizardIngredientsButton(discord.ui.View):
    """Ephemeral view with a single button that opens the ingredients modal."""

    def __init__(self, wizard_view: "AddRecipeWizardView"):
        super().__init__(timeout=600)
        self._wizard_view = wizard_view

    @discord.ui.button(label="Next: Add Ingredients", style=discord.ButtonStyle.primary)
    async def open_ingredients(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WizardIngredientsModal(self._wizard_view)
        await interaction.response.send_modal(modal)


class AddRecipeWizardModal(discord.ui.Modal, title="Add Recipe (Step 1/3)"):
    name = discord.ui.TextInput(label="Name", required=True, max_length=100)
    description = discord.ui.TextInput(
        label="Description", style=discord.TextStyle.paragraph,
        required=False, max_length=1000
    )
    servings = discord.ui.TextInput(label="Servings (required)", required=True, max_length=10)
    prep_time = discord.ui.TextInput(label="Prep Time (minutes)", required=False, max_length=10)
    cook_time = discord.ui.TextInput(label="Cook Time (minutes)", required=False, max_length=10)

    def __init__(self, wizard_view: "AddRecipeWizardView"):
        super().__init__()
        self._wizard_view = wizard_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            servings = int(_text_value(self.servings))
            if servings <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Servings must be a positive whole number."), ephemeral=True
            )
            return

        try:
            prep = int(_text_value(self.prep_time)) if _text_value(self.prep_time) else None
            cook = int(_text_value(self.cook_time)) if _text_value(self.cook_time) else None
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Prep time and cook time must be whole numbers (minutes)."),
                ephemeral=True
            )
            return

        self._wizard_view.metadata = {
            "name": _text_value(self.name),
            "description": _text_value(self.description) or None,
            "servings": servings,
            "prep_time": prep,
            "cook_time": cook,
        }
        button_view = _WizardIngredientsButton(self._wizard_view)
        await interaction.response.send_message(
            embed=success_embed("**Step 1/3 complete** — Recipe details captured."),
            view=button_view,
            ephemeral=True,
        )
```

- [ ] **Step 5: Run both tests to verify they pass**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_modal_stores_metadata_and_sends_button tests/test_recipes.py::test_wizard_modal_invalid_servings_sends_error -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: add AddRecipeWizardModal and ingredients button view

Modal 1 of the wizard validates metadata and presents a 'Next: Add
Ingredients' button to continue the flow."
```

---

### Task 3: WizardIngredientsModal (Modal 2)

Parses ingredient text and stores results on the wizard view. On success, responds with a step-complete message plus a "Next: Add Instructions" button.

**Files:**
- Modify: `recipebot/cogs/recipes.py` (add class after `_WizardIngredientsButton`)
- Test: `tests/test_recipes.py`

- [ ] **Step 1: Write failing test for ingredients modal happy path**

```python
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
```

- [ ] **Step 2: Write failing test for parse error**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_ingredients_modal_stores_and_sends_button tests/test_recipes.py::test_wizard_ingredients_modal_parse_error -v`
Expected: FAIL — `ImportError: cannot import name 'WizardIngredientsModal'`

- [ ] **Step 4: Implement WizardIngredientsModal**

Add in `recipebot/cogs/recipes.py` after `_WizardIngredientsButton`:

```python
class _WizardInstructionsButton(discord.ui.View):
    """Ephemeral view with a single button that opens the instructions modal."""

    def __init__(self, wizard_view: "AddRecipeWizardView"):
        super().__init__(timeout=600)
        self._wizard_view = wizard_view

    @discord.ui.button(label="Next: Add Instructions", style=discord.ButtonStyle.primary)
    async def open_instructions(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WizardInstructionsModal(self._wizard_view)
        await interaction.response.send_modal(modal)


class WizardIngredientsModal(discord.ui.Modal, title="Add Ingredients (Step 2/3)"):
    ingredients_text = discord.ui.TextInput(
        label="Ingredients (name, qty, unit, category)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
        placeholder="flour, 2, cup, pantry\neggs, 3, , dairy",
    )

    def __init__(self, wizard_view: "AddRecipeWizardView"):
        super().__init__()
        self._wizard_view = wizard_view

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.parsers import parse_ingredients
        text = self.ingredients_text.value or self.ingredients_text.default or ""
        items, errors = parse_ingredients(text)
        if errors:
            lines = "\n".join(f"Line {e.line_number}: {e.reason}" for e in errors)
            await interaction.response.send_message(
                embed=error_embed(f"Fix these errors and resubmit:\n```{lines}```"),
                ephemeral=True,
            )
            return
        self._wizard_view.ingredients = items
        button_view = _WizardInstructionsButton(self._wizard_view)
        await interaction.response.send_message(
            embed=success_embed("**Step 2/3 complete** — Ingredients captured."),
            view=button_view,
            ephemeral=True,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_ingredients_modal_stores_and_sends_button tests/test_recipes.py::test_wizard_ingredients_modal_parse_error -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: add WizardIngredientsModal and instructions button view

Modal 2 of the wizard parses ingredients and presents a 'Next: Add
Instructions' button to continue the flow."
```

---

### Task 4: WizardInstructionsModal (Modal 3)

Parses instruction text and calls `wizard_view.finalize()` to save everything.

**Files:**
- Modify: `recipebot/cogs/recipes.py` (add class after `_WizardInstructionsButton`)
- Test: `tests/test_recipes.py`

- [ ] **Step 1: Write failing test for instructions modal happy path (full wizard end-to-end)**

```python
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
```

- [ ] **Step 2: Write failing test for empty instructions**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_instructions_modal_triggers_finalize tests/test_recipes.py::test_wizard_instructions_modal_empty_rejects -v`
Expected: FAIL — `ImportError: cannot import name 'WizardInstructionsModal'`

- [ ] **Step 4: Implement WizardInstructionsModal**

Add in `recipebot/cogs/recipes.py` after `_WizardInstructionsButton`:

```python
class WizardInstructionsModal(discord.ui.Modal, title="Add Instructions (Step 3/3)"):
    instructions_text = discord.ui.TextInput(
        label="Steps (one per line)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
        placeholder="Boil water\nAdd pasta\nCook 10 minutes\nDrain and serve",
    )

    def __init__(self, wizard_view: "AddRecipeWizardView"):
        super().__init__()
        self._wizard_view = wizard_view

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.parsers import parse_instructions
        text = self.instructions_text.value or self.instructions_text.default or ""
        steps = parse_instructions(text)
        if not steps:
            await interaction.response.send_message(
                embed=error_embed("No instructions provided."), ephemeral=True
            )
            return
        self._wizard_view.instructions = steps
        await self._wizard_view.finalize(interaction)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_instructions_modal_triggers_finalize tests/test_recipes.py::test_wizard_instructions_modal_empty_rejects -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: add WizardInstructionsModal (final wizard step)

Modal 3 parses instructions and triggers finalize to save the complete
recipe in one DB transaction."
```

---

### Task 5: Rewire `/recipebot add` command to use wizard

Switch the existing `add` command to create the wizard view and modal instead of the old `AddRecipeModal`.

**Files:**
- Modify: `recipebot/cogs/recipes.py` (`RecipesCog.add` method, ~lines 355-359)
- Test: `tests/test_recipes.py`

- [ ] **Step 1: Write failing test for the add command sending wizard modal**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_recipes.py::test_add_command_sends_wizard_modal -v`
Expected: FAIL — `AssertionError: isinstance` check fails (still sends `AddRecipeModal`)

- [ ] **Step 3: Rewire the add command**

In `recipebot/cogs/recipes.py`, replace the `add` method body:

```python
@recipebot_group.command(name="add", description="Add a new recipe")
async def add(self, interaction: discord.Interaction):
    wizard_view = AddRecipeWizardView(
        session_factory=self.bot.session_factory,
        guild_id=str(interaction.guild_id),
        guild_name=interaction.guild.name,
        user_id=str(interaction.user.id),
    )
    modal = AddRecipeWizardModal(wizard_view)
    await interaction.response.send_modal(modal)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_recipes.py::test_add_command_sends_wizard_modal -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify nothing is broken**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: rewire /recipebot add to use the 3-step wizard flow

The add command now launches the chained modal wizard instead of the
single AddRecipeModal. Existing standalone commands unchanged."
```

---

### Task 6: Full integration test — simulate complete wizard flow

One test that exercises all three modals in sequence, verifying the all-or-nothing behavior end-to-end.

**Files:**
- Test: `tests/test_recipes.py`

- [ ] **Step 1: Write the full-flow integration test**

```python
@pytest.mark.asyncio
async def test_wizard_full_flow_end_to_end(session, bot, mock_interaction):
    """Simulate the complete 3-modal wizard flow from /recipebot add to final save."""
    from recipebot.cogs.recipes import AddRecipeWizardModal, AddRecipeWizardView
    from unittest.mock import AsyncMock, MagicMock

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
    modal2 = None
    interaction2 = MagicMock()
    interaction2.response.send_modal = AsyncMock()
    interaction2.response.send_message = AsyncMock()
    # Click the button
    await button_view_1.open_ingredients.callback(button_view_1, interaction2, None)
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
    await button_view_2.open_instructions.callback(button_view_2, interaction3, None)
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_recipes.py::test_wizard_full_flow_end_to_end -v`
Expected: PASS

- [ ] **Step 3: Run full test suite one final time**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_recipes.py
git commit -m "test: add full end-to-end integration test for recipe wizard flow

Simulates all 3 modals in sequence verifying all-or-nothing behavior
and correct final recipe creation."
```
