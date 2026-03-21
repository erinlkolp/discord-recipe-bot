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
            upsert_guild(session, str(interaction.guild_id), interaction.guild.name)
            recipe = session.get(Recipe, self._recipe_id)
            if not recipe:
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
            if recipe:
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


class SearchPaginationView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(self, results: list[Recipe]):
        super().__init__(timeout=60)
        self._results = results
        self._page = 0

    def current_embed(self) -> discord.Embed:
        start = self._page * self.PAGE_SIZE
        page_results = self._results[start:start + self.PAGE_SIZE]
        total_pages = (len(self._results) - 1) // self.PAGE_SIZE + 1
        embed = discord.Embed(title=f"Search Results (page {self._page + 1}/{total_pages})")
        for r in page_results:
            embed.add_field(name=r.name, value=r.description or "No description.", inline=False)
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
            upsert_guild(session, str(interaction.guild_id), interaction.guild.name)
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
    async def search(
        self,
        interaction: discord.Interaction,
        by: str = "name",
        query: str = "",
    ):
        with self.bot.session_factory() as session:
            guild_id = str(interaction.guild_id)
            if by == "name":
                results = session.query(Recipe).filter(
                    Recipe.guild_id == guild_id,
                    Recipe.name.ilike(f"%{query}%")
                ).all()
            elif by == "ingredient":
                from recipebot.db.models import Ingredient
                results = (
                    session.query(Recipe)
                    .join(Ingredient)
                    .filter(Recipe.guild_id == guild_id, Ingredient.name.ilike(f"%{query}%"))
                    .distinct().all()
                )
            elif by == "tag":
                from recipebot.db.models import Tag
                results = (
                    session.query(Recipe)
                    .join(Tag)
                    .filter(Recipe.guild_id == guild_id, Tag.tag_name.ilike(f"%{query}%"))
                    .distinct().all()
                )
            else:
                results = []

            if not results:
                await interaction.response.send_message(
                    embed=error_embed("No recipes found."), ephemeral=True
                )
                return
            if len(results) <= 5:
                embed = discord.Embed(title=f"Search results for '{query}'")
                for r in results:
                    embed.add_field(name=r.name, value=r.description or "No description.", inline=False)
                await interaction.response.send_message(embed=embed)
            else:
                view = SearchPaginationView(results)
                await interaction.response.send_message(embed=view.current_embed(), view=view)

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


async def setup(bot):
    await bot.add_cog(RecipesCog(bot))
