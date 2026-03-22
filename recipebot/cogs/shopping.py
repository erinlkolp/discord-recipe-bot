import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from recipebot.db.models import MealPlan, MealPlanEntry, ShoppingList, ShoppingListItem
from recipebot.db.connection import upsert_guild, current_week_start
from recipebot.cogs.recipes import recipebot_group, error_embed, success_embed
from recipebot.parsers import aggregate_shopping_items

CATEGORY_ORDER = ['produce', 'dairy', 'meat', 'seafood', 'pantry', 'frozen', 'bakery', 'other']


class ShoppingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @recipebot_group.command(name="shopping-generate",
                             description="Generate shopping list from this week's meal plan")
    async def shopping_generate(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        week = current_week_start()
        with self.bot.session_factory() as session:
            meal_plan = session.query(MealPlan).filter_by(
                guild_id=guild_id, week_start_date=week
            ).first()
            if not meal_plan:
                await interaction.response.send_message(
                    embed=error_embed(
                        "No meal plan for this week. Use `/recipebot plan-add` to get started."
                    ),
                    ephemeral=True,
                )
                return
            if not meal_plan.entries:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Your meal plan has no entries yet. Use `/recipebot plan-add` to add recipes."
                    ),
                    ephemeral=True,
                )
                return

            upsert_guild(session, guild_id, interaction.guild.name)

            # Build raw items list for aggregation
            raw_items = []
            for entry in meal_plan.entries:
                recipe = entry.recipe
                for ing in recipe.ingredients:
                    raw_items.append({
                        "name": ing.name,
                        "quantity": ing.quantity,
                        "unit": ing.unit or "",
                        "category": ing.category or "other",
                        "entry_servings": entry.servings,
                        "recipe_servings": recipe.servings,
                    })

            aggregated = aggregate_shopping_items(raw_items)

            # Replace existing shopping list for this meal plan (atomic)
            existing = session.query(ShoppingList).filter_by(meal_plan_id=meal_plan.id).first()
            if existing:
                session.delete(existing)
                # No commit here — keep the delete and insert in one transaction

            sl = ShoppingList(
                guild_id=guild_id,
                meal_plan_id=meal_plan.id,
                generated_at=datetime.now(timezone.utc),
            )
            session.add(sl)
            session.flush()  # Get sl.id without committing
            for item in aggregated:
                session.add(ShoppingListItem(
                    shopping_list_id=sl.id,
                    ingredient_name=item['ingredient_name'],
                    total_quantity=item['total_quantity'],
                    unit=item['unit'],
                    category=item['category'],
                ))
            session.commit()  # Single commit: delete old + insert new
        await interaction.response.send_message(
            embed=success_embed(
                f"Shopping list generated with {len(aggregated)} item(s). "
                f"Use `/recipebot shopping-view` to see it."
            ),
            ephemeral=True,
        )

    @recipebot_group.command(name="shopping-view",
                             description="View this week's shopping list")
    async def shopping_view(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        week = current_week_start()
        with self.bot.session_factory() as session:
            meal_plan = session.query(MealPlan).filter_by(
                guild_id=guild_id, week_start_date=week
            ).first()
            sl = None
            if meal_plan:
                sl = session.query(ShoppingList).filter_by(meal_plan_id=meal_plan.id).first()
            if not sl:
                await interaction.response.send_message(
                    embed=error_embed(
                        "No shopping list for this week. Run `/recipebot shopping-generate` first."
                    ),
                    ephemeral=True,
                )
                return
            embed = discord.Embed(
                title=f"Shopping List — Week of {week.strftime('%B %d, %Y')}",
                color=discord.Color.green(),
            )
            by_category: dict[str, list[str]] = {c: [] for c in CATEGORY_ORDER}
            for item in sl.items:
                cat = item.category or "other"
                if item.total_quantity is not None:
                    qty = f"{item.total_quantity:.2f}".rstrip('0').rstrip('.')
                else:
                    qty = ""
                unit = f" {item.unit}" if item.unit else ""
                qty_str = f": {qty}{unit}" if qty or unit else ""
                by_category[cat].append(f"• {item.ingredient_name}{qty_str}")
            for cat in CATEGORY_ORDER:
                if by_category[cat]:
                    embed.add_field(
                        name=cat.capitalize(),
                        value="\n".join(by_category[cat])[:1024],
                        inline=False,
                    )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    from recipebot.cogs.recipes import _bind_group_commands
    cog = ShoppingCog(bot)
    await bot.add_cog(cog)
    _bind_group_commands(cog)
