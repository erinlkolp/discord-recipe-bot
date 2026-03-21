import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
from recipebot.db.connection import create_db_engine, get_session_factory

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class RecipeBot(commands.Bot):
    def __init__(self, session_factory):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.session_factory = session_factory

    async def setup_hook(self):
        from recipebot.cogs.recipes import RecipesCog
        from recipebot.cogs.meal_plan import MealPlanCog
        from recipebot.cogs.shopping import ShoppingCog
        await self.add_cog(RecipesCog(self))
        await self.add_cog(MealPlanCog(self))
        await self.add_cog(ShoppingCog(self))
        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")


def main():
    engine = create_db_engine()
    session_factory = get_session_factory(engine)
    token = os.environ["DISCORD_BOT_TOKEN"]
    bot = RecipeBot(session_factory)
    bot.run(token)


if __name__ == "__main__":
    main()
