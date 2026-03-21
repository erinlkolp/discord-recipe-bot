# discord-recipe-bot

A Discord bot for managing per-server recipes, meal plans, and shopping lists using `/recipebot` slash commands.

## Tech Stack

- **Python** 3.10+ with discord.py 2.x
- **SQLAlchemy** 2.0 ORM (Percona/MySQL in production, SQLite for tests)
- **Liquibase** XML migrations
- **Docker Compose** (Percona Server + Liquibase + bot)

## Quick Start

### 1. Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application and add a Bot user
3. Enable **Server Members Intent** and **Message Content Intent** under Bot settings
4. Copy the bot token

### 2. Configure Environment

```bash
cp .env.example .env
```

Fill in `.env`:

```env
DISCORD_BOT_TOKEN=your_bot_token_here
DB_HOST=percona
DB_PORT=3306
DB_NAME=recipebot
DB_USER=recipebot
DB_PASSWORD=a_strong_password
DB_ROOT_PASSWORD=a_strong_root_password
```

### 3. Run

```bash
docker compose up --build
```

The startup sequence is:
1. Percona Server starts and becomes healthy
2. Liquibase applies migrations
3. Bot connects to Discord

### 4. Register Slash Commands (first deploy only)

```bash
SYNC_COMMANDS=1 docker compose up --build
```

Global command sync propagates to all servers within ~1 hour. Only run this when commands change — it is rate-limited to ~2 syncs per day.

### 5. Invite the Bot

Generate an invite URL in the Discord Developer Portal with the `applications.commands` and `bot` scopes, plus the `Send Messages` and `Embed Links` permissions.

---

## Commands

All commands are under `/recipebot`.

### Recipes

| Command | Description |
|---|---|
| `/recipebot add` | Add a new recipe (opens a modal) |
| `/recipebot edit <recipe>` | Edit an existing recipe |
| `/recipebot delete <recipe>` | Delete a recipe (with confirmation) |
| `/recipebot view <recipe>` | View a recipe's full details |
| `/recipebot search [by] [query]` | Search recipes by name, tag, or ingredient |
| `/recipebot ingredients <recipe>` | Set the ingredient list for a recipe |
| `/recipebot instructions <recipe>` | Set the step-by-step instructions for a recipe |
| `/recipebot tags <recipe>` | Set tags for a recipe |

### Meal Plans

| Command | Description |
|---|---|
| `/recipebot plan_add <recipe> <day> <meal_type> <servings>` | Add a recipe to this week's meal plan |
| `/recipebot plan_view` | View this week's meal plan |

### Shopping Lists

| Command | Description |
|---|---|
| `/recipebot shopping_generate` | Generate a shopping list from this week's meal plan |
| `/recipebot shopping_view` | View the current shopping list |

---

## Development

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run Tests

```bash
.venv/bin/pytest tests/ -v
```

Tests use SQLite in-memory — no database required.

### Project Layout

```
recipebot/
  bot.py              # Entry point, loads cogs
  parsers.py          # parse_ingredients, parse_instructions, aggregate_shopping_items
  db/
    models.py         # SQLAlchemy ORM models
    connection.py     # Engine, session factory, helpers
  cogs/
    recipes.py        # Recipe CRUD + search + ingredients/instructions/tags
    meal_plan.py      # Meal plan commands
    shopping.py       # Shopping list commands
liquibase/
  changelog.xml       # Master changelog
  changes/
    0001-initial-schema.xml
tests/
  conftest.py         # SQLite fixtures, mock interaction
  test_models.py
  test_parsers.py
  test_recipes.py
  test_meal_plan.py
  test_shopping.py
```

### Ingredient Format

When adding ingredients via `/recipebot ingredients`, enter one per line:

```
2 cups flour pantry
1.5 tsp salt pantry
200g chicken breast meat
```

Format: `<quantity> <unit> <name> <category>`

Valid categories: `produce`, `dairy`, `meat`, `seafood`, `pantry`, `frozen`, `bakery`, `other`

### Instruction Format

When adding instructions via `/recipebot instructions`, enter one per line — each line becomes a numbered step:

```
Preheat oven to 375F
Mix dry ingredients in a bowl
Add wet ingredients and stir until combined
```

---

## Environment Variables

| Variable | Description | Default in Docker |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Discord bot token | *(required)* |
| `DB_HOST` | Database host | `percona` |
| `DB_PORT` | Database port | `3306` |
| `DB_NAME` | Database name | `recipebot` |
| `DB_USER` | Database user | `recipebot` |
| `DB_PASSWORD` | Database password | *(required)* |
| `DB_ROOT_PASSWORD` | MySQL root password | *(required)* |
| `SYNC_COMMANDS` | Set to `1` to sync slash commands on startup | *(unset)* |
