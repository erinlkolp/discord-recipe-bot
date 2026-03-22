# CLAUDE.md

This file captures conventions and non-obvious patterns in this codebase for future Claude sessions.

## Running Tests

```bash
.venv/bin/pytest tests/ -v
```

Tests use SQLite in-memory. No database or Discord credentials needed.

## Key Architectural Patterns

### Session Factory Pattern (critical)

Modals and Views must **never** hold an open session while waiting for user input. Discord modals can stay open for up to 15 minutes before `on_submit` fires.

**Correct:** Pass `session_factory` (a callable) to the modal/view constructor. Open the session inside `on_submit` or the button callback:

```python
class MyModal(discord.ui.Modal):
    def __init__(self, session_factory, ...):
        self._session_factory = session_factory

    async def on_submit(self, interaction):
        with self._session_factory() as session:
            # do DB work here
            session.commit()
```

**Wrong:** Opening a session before sending the modal and passing the open session object.

### ORM Objects and Views

**Never** store ORM objects in a `discord.ui.View`. The session closes before the user clicks a button.

Extract to plain dicts inside the `with session:` block before the session closes:

```python
with session_factory() as session:
    rows = session.query(Recipe).filter_by(...).all()
    results = [{"name": r.name, "description": r.description} for r in rows]
# session closed — results is safe to pass to a View
view = SearchPaginationView(results)
```

### Shared `recipebot_group`

`recipebot_group` is defined at module level in `recipebot/cogs/recipes.py`. All three cogs attach commands to it.

- `recipes.py:setup()` calls `bot.tree.add_command(recipebot_group)` — **only here**
- `meal_plan.py:setup()` and `shopping.py:setup()` call only `bot.add_cog()` — they must **not** re-add the group

### Transaction Boundaries

`upsert_guild` and `_upsert_meal_plan` do **not** call `session.commit()` internally. The caller owns the commit. Always end a `with session:` block with a single `session.commit()` that covers all writes.

### `upsert_guild` Placement

Call `upsert_guild` **after** all validation guards and **before** the first write that needs the guild FK. Never call it at the top of a command before validation — if the command returns early, the merge is rolled back and the guild row is never persisted. Commands that only read or delete (e.g. `delete`, `view`, `search`) do not need `upsert_guild` at all.

### Guild Isolation

Every query that touches user data must filter by `guild_id` derived from `interaction.guild_id` (not user-supplied input). After `session.get(Recipe, id)`, always verify:

```python
if not recipe or recipe.guild_id != str(interaction.guild_id):
    # return error
```

## Slash Command Sync

Set `SYNC_COMMANDS=1` to sync global slash commands on startup. This is rate-limited (~2/day). Do not enable it for normal restarts.

## Test Fixtures (`tests/conftest.py`)

- `session` fixture: SQLite in-memory session, tables created from `Base.metadata`
- `make_session_factory(session)`: returns a `@contextmanager` function that yields the shared test session — used so `with bot.session_factory() as s:` works in tests
- `mock_interaction`: fake `discord.Interaction` with `guild_id`, `response.send_message`, `response.send_modal`, `followup.send`

## `_text_value()` Helper

Modal `TextInput` fields expose `.value` after submission but `.default` in tests (because `on_submit` is called directly without going through Discord). The helper in `recipes.py` handles both:

```python
def _text_value(field) -> str:
    return field.value or field.default or ""
```

## Ingredient / Instruction Parsing

`recipebot/parsers.py`:
- `parse_ingredients(text)` — parses `<qty> <unit> <name> <category>` lines
- `parse_instructions(text)` — splits on newlines, assigns step numbers
- `aggregate_shopping_items(items)` — aggregates by `(name.lower(), unit)`, preserves insertion order and first-seen original casing for display names, handles null quantities (items with no quantity pass through as `None`, not summed)

## Docker Compose Startup Order

`percona` → `liquibase` (migrations) → `recipebot` (bot). The bot `depends_on: liquibase: condition: service_completed_successfully`.
