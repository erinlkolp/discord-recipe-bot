import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session
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

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    async def on_submit(self, interaction: discord.Interaction):
        servings_val = _text_value(self.servings)
        try:
            servings = int(servings_val)
            if servings <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Servings must be a positive whole number."), ephemeral=True
            )
            return

        prep_val = _text_value(self.prep_time).strip()
        cook_val = _text_value(self.cook_time).strip()
        prep = int(prep_val) if prep_val else None
        cook = int(cook_val) if cook_val else None

        upsert_guild(self._session, str(interaction.guild_id), interaction.guild.name)

        now = datetime.now(timezone.utc)
        recipe = Recipe(
            guild_id=str(interaction.guild_id),
            name=_text_value(self.name).strip(),
            description=_text_value(self.description).strip() or None,
            servings=servings,
            prep_time=prep,
            cook_time=cook,
            created_by=str(interaction.user.id),
            created_at=now,
            updated_at=now,
        )
        self._session.add(recipe)
        self._session.commit()
        await interaction.response.send_message(
            embed=success_embed(f"Recipe **{recipe.name}** added! "
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

    def __init__(self, session: Session, recipe: Recipe):
        super().__init__()
        self._session = session
        self._recipe = recipe
        self.name.default = recipe.name
        self.description.default = recipe.description or ""
        self.servings.default = str(recipe.servings)
        self.prep_time.default = str(recipe.prep_time) if recipe.prep_time else ""
        self.cook_time.default = str(recipe.cook_time) if recipe.cook_time else ""

    async def on_submit(self, interaction: discord.Interaction):
        upsert_guild(self._session, str(interaction.guild_id), interaction.guild.name)
        servings_val = _text_value(self.servings)
        try:
            servings = int(servings_val)
            if servings <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Servings must be a positive whole number."), ephemeral=True
            )
            return

        self._recipe.name = _text_value(self.name).strip()
        self._recipe.description = _text_value(self.description).strip() or None
        self._recipe.servings = servings
        prep_val = _text_value(self.prep_time).strip()
        cook_val = _text_value(self.cook_time).strip()
        self._recipe.prep_time = int(prep_val) if prep_val else None
        self._recipe.cook_time = int(cook_val) if cook_val else None
        self._recipe.updated_at = datetime.now(timezone.utc)
        self._session.commit()
        await interaction.response.send_message(
            embed=success_embed(f"Recipe **{self._recipe.name}** updated."), ephemeral=True
        )


class DeleteConfirmView(discord.ui.View):
    def __init__(self, session: Session, recipe: Recipe):
        super().__init__(timeout=30)
        self._session = session
        self._recipe = recipe

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        name = self._recipe.name
        self._session.delete(self._recipe)
        self._session.commit()
        self.stop()
        await interaction.response.send_message(
            embed=success_embed(f"Recipe **{name}** deleted."), ephemeral=True
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message(
            embed=success_embed("Deletion cancelled."), ephemeral=True
        )


recipebot_group = app_commands.Group(name="recipebot", description="Recipe bot commands")


class RecipesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_recipe(self, session: Session, guild_id: str, name: str) -> Recipe | None:
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
        with self.bot.session_factory() as session:
            modal = AddRecipeModal(session)
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
            modal = EditRecipeModal(session, r)
            await interaction.response.send_modal(modal)
            await modal.wait()

    @recipebot_group.command(name="delete", description="Delete a recipe")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def delete(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            upsert_guild(session, str(interaction.guild_id), interaction.guild.name)
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            view = DeleteConfirmView(session, r)
            await interaction.response.send_message(
                embed=discord.Embed(description=f"Delete **{r.name}**? This cannot be undone."),
                view=view,
                ephemeral=True,
            )
            await view.wait()


async def setup(bot):
    await bot.add_cog(RecipesCog(bot))
