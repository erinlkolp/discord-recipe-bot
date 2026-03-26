import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from recipebot.db.models import Recipe
from recipebot.db.connection import upsert_guild


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=discord.Color.red())


def success_embed(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=discord.Color.green())


def _text_value(field: discord.ui.TextInput) -> str:
    """Return field value, falling back to default (for test compatibility)."""
    return field.value or field.default or ""


class AddRecipeModal(discord.ui.Modal, title="Add Recipe"):
    name = discord.ui.TextInput(label="Name", required=True, max_length=100)
    description = discord.ui.TextInput(
        label="Description", style=discord.TextStyle.paragraph,
        required=False, max_length=1000
    )
    servings = discord.ui.TextInput(label="Servings (required)", required=True, max_length=10)
    prep_time = discord.ui.TextInput(label="Prep Time (minutes)", required=False, max_length=10)
    cook_time = discord.ui.TextInput(label="Cook Time (minutes)", required=False, max_length=10)

    def __init__(self, session_factory):
        super().__init__()
        self._session_factory = session_factory

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

        with self._session_factory() as session:
            upsert_guild(session, str(interaction.guild_id), interaction.guild.name)
            now = datetime.now(timezone.utc)
            recipe = Recipe(
                guild_id=str(interaction.guild_id),
                name=_text_value(self.name),
                description=_text_value(self.description) or None,
                servings=servings,
                prep_time=prep,
                cook_time=cook,
                created_by=str(interaction.user.id),
                created_at=now,
                updated_at=now,
            )
            session.add(recipe)
            session.commit()
            recipe_name = recipe.name
        await interaction.response.send_message(
            embed=success_embed(f"Recipe **{recipe_name}** added! "
                                f"Use `/recipebot ingredients` and `/recipebot instructions` to complete it."),
            ephemeral=True
        )


class EditRecipeModal(discord.ui.Modal, title="Edit Recipe"):
    name = discord.ui.TextInput(label="Name", required=True, max_length=100)
    description = discord.ui.TextInput(
        label="Description", style=discord.TextStyle.paragraph,
        required=False, max_length=1000
    )
    servings = discord.ui.TextInput(label="Servings (required)", required=True, max_length=10)
    prep_time = discord.ui.TextInput(label="Prep Time (minutes)", required=False, max_length=10)
    cook_time = discord.ui.TextInput(label="Cook Time (minutes)", required=False, max_length=10)

    def __init__(self, session_factory, recipe_id: int, recipe_name: str, recipe_description: str,
                 recipe_servings: int, recipe_prep_time, recipe_cook_time):
        super().__init__()
        self._session_factory = session_factory
        self._recipe_id = recipe_id
        self.name.default = recipe_name
        self.description.default = recipe_description or ""
        self.servings.default = str(recipe_servings)
        self.prep_time.default = str(recipe_prep_time) if recipe_prep_time else ""
        self.cook_time.default = str(recipe_cook_time) if recipe_cook_time else ""

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

        with self._session_factory() as session:
            recipe = session.get(Recipe, self._recipe_id)
            if not recipe or recipe.guild_id != str(interaction.guild_id):
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            recipe.name = _text_value(self.name)
            recipe.description = _text_value(self.description) or None
            recipe.servings = servings
            recipe.prep_time = prep
            recipe.cook_time = cook
            recipe.updated_at = datetime.now(timezone.utc)
            session.commit()
            recipe_name = recipe.name
        await interaction.response.send_message(
            embed=success_embed(f"Recipe **{recipe_name}** updated."), ephemeral=True
        )


class DeleteConfirmView(discord.ui.View):
    def __init__(self, session_factory, recipe_id: int, recipe_name: str):
        super().__init__(timeout=30)
        self._session_factory = session_factory
        self._recipe_id = recipe_id
        self._recipe_name = recipe_name

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        with self._session_factory() as session:
            recipe = session.get(Recipe, self._recipe_id)
            if not recipe or recipe.guild_id != str(interaction.guild_id):
                await interaction.response.send_message(embed=error_embed("Recipe not found."), ephemeral=True)
                return
            session.delete(recipe)
            session.commit()
        self.stop()
        await interaction.response.send_message(
            embed=success_embed(f"Recipe **{self._recipe_name}** deleted."), ephemeral=True
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message(
            embed=discord.Embed(description="Deletion cancelled.", color=discord.Color.greyple()),
            ephemeral=True
        )


class IngredientsModal(discord.ui.Modal, title="Set Ingredients"):
    ingredients_text = discord.ui.TextInput(
        label="Ingredients (name, qty, unit, category)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
        placeholder="flour, 2, cup, pantry\neggs, 3, , dairy",
    )

    def __init__(self, session_factory, recipe_id: int):
        super().__init__()
        self._session_factory = session_factory
        self._recipe_id = recipe_id

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.parsers import parse_ingredients
        from recipebot.db.models import Ingredient
        text = self.ingredients_text.value or self.ingredients_text.default or ""
        items, errors = parse_ingredients(text)
        if errors:
            lines = "\n".join(f"Line {e.line_number}: {e.reason}" for e in errors)
            await interaction.response.send_message(
                embed=error_embed(f"Fix these errors and resubmit:\n```{lines}```"),
                ephemeral=True,
            )
            return
        with self._session_factory() as session:
            recipe = session.get(Recipe, self._recipe_id)
            if not recipe or recipe.guild_id != str(interaction.guild_id):
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            session.query(Ingredient).filter_by(recipe_id=self._recipe_id).delete()
            for item in items:
                session.add(Ingredient(
                    recipe_id=self._recipe_id,
                    name=item.name,
                    quantity=item.quantity,
                    unit=item.unit,
                    category=item.category,
                ))
            session.commit()
            recipe_name = recipe.name
        await interaction.response.send_message(
            embed=success_embed(f"Ingredients updated for **{recipe_name}**."),
            ephemeral=True,
        )


class InstructionsModal(discord.ui.Modal, title="Set Instructions"):
    instructions_text = discord.ui.TextInput(
        label="Steps (one per line)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
        placeholder="Boil water\nAdd pasta\nCook 10 minutes\nDrain and serve",
    )

    def __init__(self, session_factory, recipe_id: int):
        super().__init__()
        self._session_factory = session_factory
        self._recipe_id = recipe_id

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.parsers import parse_instructions
        from recipebot.db.models import Instruction
        text = self.instructions_text.value or self.instructions_text.default or ""
        steps = parse_instructions(text)
        if not steps:
            await interaction.response.send_message(
                embed=error_embed("No instructions provided."), ephemeral=True
            )
            return
        with self._session_factory() as session:
            recipe = session.get(Recipe, self._recipe_id)
            if not recipe or recipe.guild_id != str(interaction.guild_id):
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            session.query(Instruction).filter_by(recipe_id=self._recipe_id).delete()
            for i, text_step in enumerate(steps, start=1):
                session.add(Instruction(
                    recipe_id=self._recipe_id, step_number=i, instruction_text=text_step
                ))
            session.commit()
            recipe_name = recipe.name
        await interaction.response.send_message(
            embed=success_embed(f"Instructions updated for **{recipe_name}**."),
            ephemeral=True,
        )


class TagModal(discord.ui.Modal, title="Set Tags"):
    tags_text = discord.ui.TextInput(
        label="Tags (comma-separated)",
        required=False,
        max_length=500,
        placeholder="italian, pasta, dinner",
    )

    def __init__(self, session_factory, recipe_id: int, current_tags: str = ""):
        super().__init__()
        self._session_factory = session_factory
        self._recipe_id = recipe_id
        self.tags_text.default = current_tags

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.db.models import Tag
        text = self.tags_text.value or self.tags_text.default or ""
        with self._session_factory() as session:
            recipe = session.get(Recipe, self._recipe_id)
            if not recipe or recipe.guild_id != str(interaction.guild_id):
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            session.query(Tag).filter_by(recipe_id=self._recipe_id).delete()
            raw = text.strip()
            if raw:
                for tag in {t.strip().lower() for t in raw.split(",") if t.strip()}:
                    session.add(Tag(recipe_id=self._recipe_id, tag_name=tag))
            session.commit()
            recipe_name = recipe.name
        await interaction.response.send_message(
            embed=success_embed(f"Tags updated for **{recipe_name}**."),
            ephemeral=True,
        )


class SearchPaginationView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(self, results: list[dict]):
        super().__init__(timeout=60)
        self._results = results
        self._page = 0

    def current_embed(self) -> discord.Embed:
        start = self._page * self.PAGE_SIZE
        page_results = self._results[start:start + self.PAGE_SIZE]
        total_pages = (len(self._results) - 1) // self.PAGE_SIZE + 1
        embed = discord.Embed(title=f"Search Results (page {self._page + 1}/{total_pages})")
        for r in page_results:
            embed.add_field(name=r["name"], value=r["description"] or "No description.", inline=False)
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._page > 0:
            self._page -= 1
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = (len(self._results) - 1) // self.PAGE_SIZE
        if self._page < max_page:
            self._page += 1
        await interaction.response.edit_message(embed=self.current_embed(), view=self)


class _WizardIngredientsButton(discord.ui.View):
    """Ephemeral view with a single button that opens the ingredients modal."""

    def __init__(self, wizard_view: "AddRecipeWizardView"):
        super().__init__(timeout=600)
        self._wizard_view = wizard_view

    @discord.ui.button(label="Next: Add Ingredients", style=discord.ButtonStyle.primary)
    async def open_ingredients(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WizardIngredientsModal(self._wizard_view)
        await interaction.response.send_modal(modal)


class _WizardInstructionsButton(discord.ui.View):
    """Ephemeral view with a single button that opens the instructions modal."""

    def __init__(self, wizard_view: "AddRecipeWizardView"):
        super().__init__(timeout=600)
        self._wizard_view = wizard_view

    @discord.ui.button(label="Next: Add Instructions", style=discord.ButtonStyle.primary)
    async def open_instructions(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WizardInstructionsModal(self._wizard_view)
        await interaction.response.send_modal(modal)


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
            session.refresh(recipe)
            embed = RecipesCog._build_recipe_embed(recipe)
            session.commit()
        self.stop()
        await interaction.response.send_message(embed=embed)


recipebot_group = app_commands.Group(name="recipebot", description="Recipe bot commands")


class RecipesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_recipe(self, session, guild_id: str, name: str) -> Recipe | None:
        return session.query(Recipe).filter_by(guild_id=guild_id, name=name).first()

    async def _recipe_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        with self.bot.session_factory() as session:
            q = session.query(Recipe.name).filter(
                Recipe.guild_id == str(interaction.guild_id),
                Recipe.name.ilike(f"{current}%")
            ).limit(25).all()
        return [app_commands.Choice(name=r.name, value=r.name) for r in q]

    @recipebot_group.command(name="add", description="Add a new recipe")
    async def add(self, interaction: discord.Interaction):
        modal = AddRecipeModal(self.bot.session_factory)
        await interaction.response.send_modal(modal)
        await modal.wait()

    @recipebot_group.command(name="edit", description="Edit an existing recipe")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def edit(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            modal = EditRecipeModal(
                self.bot.session_factory, r.id, r.name, r.description,
                r.servings, r.prep_time, r.cook_time
            )
        await interaction.response.send_modal(modal)
        await modal.wait()

    @recipebot_group.command(name="delete", description="Delete a recipe")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def delete(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            recipe_id, recipe_name = r.id, r.name
        view = DeleteConfirmView(self.bot.session_factory, recipe_id, recipe_name)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"Delete **{recipe_name}**? This cannot be undone.",
                                color=discord.Color.orange()),
            view=view,
            ephemeral=True,
        )
        await view.wait()

    @recipebot_group.command(name="view", description="View a recipe")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def view(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            embed = self._build_recipe_embed(r)
        await interaction.response.send_message(embed=embed)

    @recipebot_group.command(name="search", description="Search recipes by name, ingredient, or tag")
    @app_commands.describe(by="Search by: name, ingredient, or tag", query="Search query")
    @app_commands.choices(by=[
        app_commands.Choice(name="Name", value="name"),
        app_commands.Choice(name="Ingredient", value="ingredient"),
        app_commands.Choice(name="Tag", value="tag"),
    ])
    async def search(
        self,
        interaction: discord.Interaction,
        by: str = "name",
        query: str = "",
    ):
        with self.bot.session_factory() as session:
            guild_id = str(interaction.guild_id)
            if by == "name":
                rows = session.query(Recipe).filter(
                    Recipe.guild_id == guild_id,
                    Recipe.name.ilike(f"%{query}%")
                ).all()
            elif by == "ingredient":
                from recipebot.db.models import Ingredient
                rows = (
                    session.query(Recipe)
                    .join(Ingredient)
                    .filter(Recipe.guild_id == guild_id, Ingredient.name.ilike(f"%{query}%"))
                    .distinct().all()
                )
            elif by == "tag":
                from recipebot.db.models import Tag
                rows = (
                    session.query(Recipe)
                    .join(Tag)
                    .filter(Recipe.guild_id == guild_id, Tag.tag_name.ilike(f"%{query}%"))
                    .distinct().all()
                )
            else:
                rows = []

            if not rows:
                await interaction.response.send_message(
                    embed=error_embed("No recipes found."), ephemeral=True
                )
                return

            # Convert to plain dicts while session is still open
            results = [{"name": r.name, "description": r.description} for r in rows]

        if len(results) <= 5:
            embed = discord.Embed(title=f"Search results for '{query}'")
            for r in results:
                embed.add_field(name=r["name"], value=r["description"] or "No description.", inline=False)
            await interaction.response.send_message(embed=embed)
        else:
            view = SearchPaginationView(results)
            await interaction.response.send_message(embed=view.current_embed(), view=view)

    @recipebot_group.command(name="ingredients", description="Set ingredients for a recipe (replaces existing)")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def ingredients(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            recipe_id = r.id
        modal = IngredientsModal(self.bot.session_factory, recipe_id)
        await interaction.response.send_modal(modal)
        await modal.wait()

    @recipebot_group.command(name="instructions", description="Set instructions for a recipe (replaces existing)")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def instructions(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            recipe_id = r.id
        modal = InstructionsModal(self.bot.session_factory, recipe_id)
        await interaction.response.send_modal(modal)
        await modal.wait()

    @recipebot_group.command(name="tag", description="Set tags for a recipe")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def tag(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            recipe_id = r.id
            current_tags = ", ".join(t.tag_name for t in r.tags)
        modal = TagModal(self.bot.session_factory, recipe_id, current_tags)
        await interaction.response.send_modal(modal)
        await modal.wait()

    @staticmethod
    def _build_recipe_embed(recipe: Recipe) -> discord.Embed:
        embed = discord.Embed(title=recipe.name, description=recipe.description or "")
        meta_parts = [f"Servings: {recipe.servings}"]
        if recipe.prep_time:
            meta_parts.append(f"Prep: {recipe.prep_time}min")
        if recipe.cook_time:
            meta_parts.append(f"Cook: {recipe.cook_time}min")
        embed.add_field(name="Details", value=" | ".join(meta_parts), inline=False)
        if recipe.tags:
            embed.add_field(name="Tags", value=", ".join(t.tag_name for t in recipe.tags), inline=False)
        if recipe.ingredients:
            lines = []
            for ing in recipe.ingredients:
                qty = f"{ing.quantity} {ing.unit}".strip() if ing.quantity else ing.unit or ""
                lines.append(f"• {ing.name}" + (f" ({qty})" if qty else ""))
            embed.add_field(name="Ingredients", value="\n".join(lines)[:1024], inline=False)
        if recipe.instructions:
            lines = [f"{ins.step_number}. {ins.instruction_text}" for ins in recipe.instructions]
            embed.add_field(name="Instructions", value="\n".join(lines)[:1024], inline=False)
        return embed


def _bind_group_commands(cog):
    """Bind cog instance to commands on the shared recipebot_group.

    CogMeta skips commands with parent != None, so commands added via
    @recipebot_group.command() never get their cog binding set automatically.
    """
    for value in type(cog).__dict__.values():
        if isinstance(value, app_commands.Command) and value.parent is not None:
            value.binding = cog


async def setup(bot):
    cog = RecipesCog(bot)
    await bot.add_cog(cog)
    _bind_group_commands(cog)
    bot.tree.add_command(recipebot_group)
