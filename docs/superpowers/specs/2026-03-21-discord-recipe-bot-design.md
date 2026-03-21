# Discord Recipe Bot — Design Spec

**Date:** 2026-03-21
**Status:** Approved

---

## Overview

A Discord bot that manages recipes, ingredients, meal plans, and shopping lists on a per-server basis. Deployed as a Docker Compose stack with Percona Server (MySQL), Liquibase for migrations, and a Python discord.py bot.

---

## Architecture

### Containers (docker-compose)

| Service | Image | Role |
|---|---|---|
| `percona` | `percona/percona-server:latest` | MySQL-compatible database, data on named volume |
| `liquibase` | `liquibase/liquibase:latest` | Runs DB migrations on startup, then exits |
| `recipebot` | Custom image built from `Dockerfile` | Discord bot, starts after liquibase completes |

**Startup order:** `percona` (healthy) → `liquibase` (completed successfully) → `recipebot`

**Liquibase volume strategy:** Changelog files live on the host (`./liquibase/`) and are bind-mounted to `/liquibase/changelog` inside the container. Docker creates `/liquibase/changelog` as a new subdirectory — it does not shadow the existing Liquibase binary files at `/liquibase/liquibase`, `/liquibase/*.jar`, etc. The `--changelog-file=changelog/changelog.xml` argument is relative to Liquibase's working directory (`/liquibase`), resolving to `/liquibase/changelog/changelog.xml` in the container, which corresponds to `./liquibase/changelog.xml` on the host.

### Project Structure

```
recipebot/
  bot.py              # Entry point, registers cogs, connects to DB
  cogs/
    recipes.py        # /recipebot add, view, edit, delete, search
    meal_plan.py      # /recipebot plan add, plan view
    shopping.py       # /recipebot shopping generate, shopping view
  db/
    connection.py     # SQLAlchemy engine + session factory
    models.py         # ORM model definitions
liquibase/
  changelog.xml       # Master changelog (includes all changesets) — host-side, mounted into container
  changes/            # One XML file per migration version — host-side, mounted into container
Dockerfile            # Bot image
docker-compose.yml
.env.example
requirements.txt
```

### Configuration

Environment variables loaded via `.env`:

```
DISCORD_BOT_TOKEN=
DB_HOST=percona
DB_PORT=3306
DB_NAME=recipebot
DB_USER=recipebot
DB_PASSWORD=
DB_ROOT_PASSWORD=
```

---

## Data Model

### Tables

**guilds**
- `guild_id` VARCHAR PK — Discord guild (server) snowflake ID
- `name` VARCHAR — Guild name (informational)

**Auto-population:** A `guilds` row is upserted (`INSERT ... ON DUPLICATE KEY UPDATE`) on every slash command invocation before any other DB operation, using the guild ID and name from the Discord interaction context. This ensures the FK constraint on downstream tables is always satisfied without a separate setup step.

**recipes**
- `id` INT PK AUTO_INCREMENT
- `guild_id` VARCHAR NOT NULL FK → guilds
- `name` VARCHAR NOT NULL
- `description` TEXT
- `servings` INT NOT NULL CHECK (servings > 0) — required; used as denominator in shopping list scaling
- `prep_time` INT — minutes
- `cook_time` INT — minutes
- `created_by` VARCHAR — Discord user ID
- `created_at` DATETIME
- `updated_at` DATETIME — set on every edit

**ingredients**
- `id` INT PK AUTO_INCREMENT
- `recipe_id` INT FK → recipes ON DELETE CASCADE
- `name` VARCHAR NOT NULL
- `quantity` DECIMAL(10,3)
- `unit` VARCHAR — e.g. "cup", "tbsp", "g"
- `category` ENUM NOT NULL DEFAULT 'other' — produce, dairy, meat, seafood, pantry, frozen, bakery, other

**instructions**
- `id` INT PK AUTO_INCREMENT
- `recipe_id` INT FK → recipes ON DELETE CASCADE
- `step_number` INT NOT NULL
- `instruction_text` TEXT NOT NULL

**tags**
- `id` INT PK AUTO_INCREMENT
- `recipe_id` INT FK → recipes ON DELETE CASCADE
- `tag_name` VARCHAR NOT NULL

**meal_plans**
- `id` INT PK AUTO_INCREMENT
- `guild_id` VARCHAR NOT NULL FK → guilds
- `week_start_date` DATE NOT NULL — Monday of the planned week
- `created_by` VARCHAR — Discord user ID
- UNIQUE KEY on `(guild_id, week_start_date)`

**meal_plan_entries**
- `id` INT PK AUTO_INCREMENT
- `meal_plan_id` INT FK → meal_plans ON DELETE CASCADE
- `recipe_id` INT FK → recipes ON DELETE CASCADE
- `day_of_week` ENUM — monday, tuesday, wednesday, thursday, friday, saturday, sunday
- `meal_type` ENUM — breakfast, lunch, dinner, snack
- `servings` INT NOT NULL CHECK (servings > 0)
- UNIQUE KEY on `(meal_plan_id, day_of_week, meal_type, recipe_id)` — prevents duplicate entries for the same recipe/slot combination

**Application-layer guild isolation guard:** Before inserting a `meal_plan_entry`, the application verifies that `recipes.guild_id` matches `meal_plans.guild_id`. This prevents cross-guild recipe association that MySQL cannot enforce with a simple FK.

**Duplicate handling:** If `plan add` is called with a combination that already exists, the application responds with an ephemeral "This recipe is already in your meal plan for that slot."

**Meal plan upsert pattern:** `INSERT INTO meal_plans (guild_id, week_start_date, created_by) VALUES (...) ON DUPLICATE KEY UPDATE created_by = VALUES(created_by)` — the no-op update satisfies MySQL's upsert syntax while leaving existing records unchanged.

**shopping_lists**
- `id` INT PK AUTO_INCREMENT
- `guild_id` VARCHAR NOT NULL FK → guilds — denormalized for direct scoping queries
- `meal_plan_id` INT FK → meal_plans ON DELETE CASCADE
- `generated_at` DATETIME

**shopping_list_items**
- `id` INT PK AUTO_INCREMENT
- `shopping_list_id` INT FK → shopping_lists ON DELETE CASCADE
- `ingredient_name` VARCHAR NOT NULL
- `total_quantity` DECIMAL(10,3)
- `unit` VARCHAR
- `category` ENUM NOT NULL DEFAULT 'other' — same values as ingredients.category

### Key Behaviors
- All recipe data is scoped to `guild_id` — servers are fully isolated
- Shopping list generation aggregates ingredients across all meal plan entries, scaling by `entry.servings / recipe.servings`, and sums quantities for identical `(ingredient_name, unit)` pairs
- If the same ingredient appears with different units across recipes (e.g., "flour" in "cups" and "flour" in "grams"), each `(name, unit)` combination produces a separate line item — no unit conversion is performed
- Shopping list items are grouped by category when displayed; items with no category default to "other"
- `shopping_lists.guild_id` is denormalized to allow direct `WHERE guild_id = ?` queries without joins
- **Active meal plan** for `shopping generate` and `plan view` is defined as the meal plan for the current ISO calendar week (Monday–Sunday). If no meal plan exists for the current week, the user is prompted to add recipes via `plan add`.

---

## Commands

All commands use the `/recipebot` slash command group.

### Recipe Management

| Subcommand | Description | Input |
|---|---|---|
| `/recipebot add` | Create a new recipe shell | Modal: name, description, servings (required), prep time, cook time — 5 fields, Discord's maximum |
| `/recipebot ingredients <recipe>` | Replace all ingredients for a recipe | Modal: one ingredient per line — `name, quantity, unit, category` (max ~50 ingredients per Discord's 4000-char modal limit) |
| `/recipebot instructions <recipe>` | Replace all instructions for a recipe | Modal: one step per line; `step_number` is assigned by line position (1-indexed) |
| `/recipebot tag <recipe>` | Set tags for a recipe | Modal: comma-separated tag names in a single text field |
| `/recipebot view <recipe>` | Display full recipe as formatted embed | Autocomplete on recipe name |
| `/recipebot search` | Search recipes by name, ingredient, or tag | Inline options |
| `/recipebot edit <recipe>` | Edit recipe metadata | Pre-filled modal: name, description, servings, prep time, cook time — 5 fields |
| `/recipebot delete <recipe>` | Delete a recipe | Confirmation button prompt |

### Meal Planning

| Subcommand | Description | Input |
|---|---|---|
| `/recipebot plan add` | Add a recipe to the current week's meal plan | Options: recipe (autocomplete, required), day, meal type, servings (all required) |
| `/recipebot plan view` | Show the current ISO week's meal plan | Formatted embed by day |

**Meal plan creation:** `plan add` implicitly upserts the `meal_plans` record for the current guild + ISO week before inserting the entry. No separate "create plan" command is needed.

**Week scope:** All meal plan commands (`plan add`, `plan view`) and shopping commands (`shopping generate`, `shopping view`) operate exclusively on the **current ISO calendar week** (Monday–Sunday). There is no `week` parameter — past and future week management is out of scope for v1.

### Shopping

| Subcommand | Description | Input |
|---|---|---|
| `/recipebot shopping generate` | Generate shopping list from active meal plan | Aggregates + scales all ingredients for the current week |
| `/recipebot shopping view` | Display the shopping list for the current ISO week | Embed with sections per ingredient category |

### UX Notes
- Recipe name arguments use Discord autocomplete (filtered by guild)
- Search results paginated if more than 5 results (using discord.py view buttons)
- `add` creates the recipe shell; `ingredients` and `instructions` are separate commands due to Discord's 5-field modal limit
- `ingredients` and `instructions` are **replace** operations: existing rows for the recipe are deleted before new rows are inserted (DELETE + INSERT in a transaction)
- Errors displayed as ephemeral (visible only to the invoking user)

---

## Docker Compose

```yaml
services:
  percona:
    image: percona/percona-server:latest
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME}
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
    volumes:
      - percona_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  liquibase:
    image: liquibase/liquibase:latest
    depends_on:
      percona:
        condition: service_healthy
    volumes:
      - ./liquibase:/liquibase/changelog
    command: >
      --url=jdbc:mysql://${DB_HOST}:${DB_PORT}/${DB_NAME}
      --username=${DB_USER}
      --password=${DB_PASSWORD}
      --changelog-file=changelog/changelog.xml
      update

  recipebot:
    build: .
    depends_on:
      liquibase:
        condition: service_completed_successfully
    environment:
      DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN}
      DB_HOST: ${DB_HOST}
      DB_PORT: ${DB_PORT}
      DB_NAME: ${DB_NAME}
      DB_USER: ${DB_USER}
      DB_PASSWORD: ${DB_PASSWORD}
    restart: unless-stopped

volumes:
  percona_data:
```

**Credential substitution:** Docker Compose interpolates `${VAR}` references in the `command` field at parse time using values from the `.env` file. The Liquibase service has no `environment:` block — credentials are passed directly on the command line via Compose substitution, not as container environment variables.

---

## Dockerfile

**Bot image (`Dockerfile`):**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY recipebot/ ./recipebot/
CMD ["python", "recipebot/bot.py"]
```

---

## Liquibase Migrations

- Master file: `liquibase/changelog.xml` — includes all changesets in order
- Each migration: `liquibase/changes/NNNN-description.xml`
- Initial migration (`0001-initial-schema.xml`) creates all tables with FK constraints and indexes on `guild_id`

---

## Error Handling

- DB connection failures at startup: bot logs error and exits (docker restarts it)
- Command errors: caught per-cog, respond with ephemeral error embed
- Missing recipe (autocomplete bypassed): respond with ephemeral "Recipe not found" — applies to all commands that reference a recipe by name, including `plan add`
- Shopping list generation with no meal plan for current guild/week: respond with ephemeral "No meal plan found for this week. Use `/recipebot plan add` to get started."
- Shopping list generation with a meal plan that has zero entries: respond with ephemeral "Your meal plan for this week has no entries yet. Use `/recipebot plan add` to add recipes."
- `shopping generate` when a shopping list already exists for the current week's meal plan: replace it — delete `shopping_list_items` first (FK child), then delete the `shopping_lists` record for that `meal_plan_id`, then insert a fresh list (all in one transaction; `ON DELETE CASCADE` on `shopping_list_items` also ensures safe deletion if order is reversed)
- `shopping view` scoping: shows the shopping list for the **current ISO week's meal plan**, not globally latest. If no list exists for this week (never generated or regenerated), respond with ephemeral "No shopping list found for this week. Run `/recipebot shopping generate` first."
- `/recipebot ingredients` modal parse error (wrong number of fields, non-numeric quantity, invalid category): reject the entire submission and respond with an ephemeral error listing the bad line(s) — no partial writes; category matching is case-insensitive (normalize input to lowercase before matching against the ENUM)
- `/recipebot instructions` modal parse error (empty line in the middle of input): skip blank lines silently; `step_number` is derived from the position among non-blank lines
- Cross-guild recipe association attempt (detected at app layer): respond with ephemeral "That recipe does not belong to this server."
- `plan add` duplicate entry (UNIQUE constraint violation): respond with ephemeral "This recipe is already in your meal plan for that slot."

---

## Out of Scope

- User authentication or role-based permissions (all server members have full access)
- Cross-server recipe sharing
- Recipe import from URLs or external sources
- Nutritional information
- Past or future week meal plan management (v1 operates on current ISO week only)
