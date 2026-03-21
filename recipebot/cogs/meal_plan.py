import discord
from discord import app_commands
from discord.ext import commands
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from recipebot.db.models import Recipe, MealPlan, MealPlanEntry
from recipebot.db.connection import upsert_guild, current_week_start
from recipebot.cogs.recipes import recipebot_group, error_embed, success_embed

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack']


def _upsert_meal_plan(session: Session, guild_id: str, week: date, user_id: str) -> MealPlan:
    """Insert or update meal plan for guild+week. Uses ORM merge for DB portability."""
    existing = session.query(MealPlan).filter_by(
        guild_id=guild_id, week_start_date=week
    ).first()
    if existing:
        existing.created_by = user_id
        session.commit()
        return existing
    mp = MealPlan(guild_id=guild_id, week_start_date=week, created_by=user_id)
    session.add(mp)
    session.commit()
    return mp


class MealPlanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _recipe_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        with self.bot.session_factory() as session:
            q = session.query(Recipe.name).filter(
                Recipe.guild_id == str(interaction.guild_id),
                Recipe.name.ilike(f"{current}%")
            ).limit(25).all()
        return [app_commands.Choice(name=r.name, value=r.name) for r in q]

    @recipebot_group.command(name="plan-add", description="Add a recipe to this week's meal plan")
    @app_commands.describe(
        recipe="Recipe name",
        day="Day of the week",
        meal_type="Meal type",
        servings="Number of servings",
    )
    @app_commands.choices(
        day=[app_commands.Choice(name=d, value=d) for d in DAYS],
        meal_type=[app_commands.Choice(name=m, value=m) for m in MEAL_TYPES],
    )
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def plan_add(
        self,
        interaction: discord.Interaction,
        recipe: str,
        day: str,
        meal_type: str,
        servings: int,
    ):
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        with self.bot.session_factory() as session:
            upsert_guild(session, guild_id, interaction.guild.name)
            r = session.query(Recipe).filter_by(guild_id=guild_id, name=recipe).first()
            if not r:
                await interaction.response.send_message(
                    embed=error_embed("Recipe not found."), ephemeral=True
                )
                return
            if r.guild_id != guild_id:
                await interaction.response.send_message(
                    embed=error_embed("That recipe does not belong to this server."), ephemeral=True
                )
                return
            week = current_week_start()
            meal_plan = _upsert_meal_plan(session, guild_id, week, user_id)
            entry = MealPlanEntry(
                meal_plan_id=meal_plan.id,
                recipe_id=r.id,
                day_of_week=day,
                meal_type=meal_type,
                servings=servings,
            )
            session.add(entry)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                await interaction.response.send_message(
                    embed=error_embed("This recipe is already in your meal plan for that slot."),
                    ephemeral=True,
                )
                return
            recipe_name = r.name
        await interaction.response.send_message(
            embed=success_embed(
                f"Added **{recipe_name}** to {day.capitalize()} {meal_type} "
                f"({servings} serving{'s' if servings != 1 else ''})."
            ),
            ephemeral=True,
        )

    @recipebot_group.command(name="plan-view", description="View this week's meal plan")
    async def plan_view(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        week = current_week_start()
        with self.bot.session_factory() as session:
            meal_plan = session.query(MealPlan).filter_by(
                guild_id=guild_id, week_start_date=week
            ).first()
            if not meal_plan or not meal_plan.entries:
                await interaction.response.send_message(
                    embed=error_embed(
                        "No meal plan for this week. Use `/recipebot plan-add` to get started."
                    ),
                    ephemeral=True,
                )
                return
            embed = discord.Embed(
                title=f"Meal Plan — Week of {week.strftime('%B %d, %Y')}",
                color=discord.Color.blue(),
            )
            by_day = {d: [] for d in DAYS}
            for entry in meal_plan.entries:
                by_day[entry.day_of_week].append(
                    f"**{entry.meal_type.capitalize()}**: {entry.recipe.name} ({entry.servings} srv)"
                )
            for day in DAYS:
                if by_day[day]:
                    embed.add_field(
                        name=day.capitalize(),
                        value="\n".join(by_day[day]),
                        inline=False,
                    )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(MealPlanCog(bot))
