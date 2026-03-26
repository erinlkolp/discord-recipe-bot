# Add Recipe Wizard — Design Spec

## Problem

Creating a recipe currently requires three separate slash commands:
1. `/recipebot add` — metadata (name, description, servings, prep/cook times)
2. `/recipebot ingredients <recipe>` — ingredient list
3. `/recipebot instructions <recipe>` — step-by-step instructions

This is clunky. Users must remember the recipe name and run two follow-up commands to complete a recipe.

## Solution

Consolidate into a single `/recipebot add` command that chains three modals in sequence, connected by ephemeral button prompts. Nothing is saved until all three modals are completed.

## Interaction Flow

```
User: /recipebot add
Bot:  → sends Modal 1 (metadata)
User: fills in name, description, servings, prep time, cook time → submits
Bot:  → validates → sends ephemeral message "Step 1/3 complete" + [Next: Add Ingredients] button
User: clicks button
Bot:  → sends Modal 2 (ingredients)
User: fills in ingredients (same format as today) → submits
Bot:  → parses & validates → sends ephemeral message "Step 2/3 complete" + [Next: Add Instructions] button
User: clicks button
Bot:  → sends Modal 3 (instructions)
User: fills in instructions (one per line) → submits
Bot:  → parses & validates → saves everything in one DB transaction → sends public recipe summary embed
```

## New Components

### `AddRecipeWizardModal` (Modal 1)

Same five fields as current `AddRecipeModal`:
- `name` (required, max 100)
- `description` (optional, paragraph, max 1000)
- `servings` (required, positive integer)
- `prep_time` (optional, integer minutes)
- `cook_time` (optional, integer minutes)

On submit:
- Validates servings/times (same logic as current `AddRecipeModal.on_submit`)
- On validation error: sends ephemeral error message, flow stops (user must re-run `/recipebot add`)
- On success: stores validated metadata on `self._wizard_view`, responds with ephemeral step-complete message + next-step view

Does NOT receive `session_factory`. No DB access at this step.

Constructor receives a reference to the `AddRecipeWizardView` instance (`wizard_view`) so it can store validated data on it.

### `WizardIngredientsModal` (Modal 2)

Same single field as current `IngredientsModal`:
- `ingredients_text` (required, paragraph, max 4000, same placeholder)

On submit:
- Calls `parse_ingredients(text)`
- On parse errors: sends ephemeral error message with line-by-line errors. Flow does NOT advance. The "Next: Add Ingredients" button on the *previous* ephemeral message remains functional — the user clicks that button again to retry. (Each modal submission is its own interaction, so consuming this interaction's response for the error does not invalidate the prior message's buttons.)
- On success: stores parsed `ParsedIngredient` objects on `self._wizard_view.ingredients`, responds with ephemeral step-complete message + next-step view

Constructor receives a reference to the `AddRecipeWizardView` instance. No `session_factory` or `recipe_id`. No DB access.

### `WizardInstructionsModal` (Modal 3)

Same single field as current `InstructionsModal`:
- `instructions_text` (required, paragraph, max 4000, same placeholder)

On submit:
- Calls `parse_instructions(text)`
- On empty: sends ephemeral error message. Flow does NOT advance. The "Next: Add Instructions" button on the *previous* ephemeral message remains functional for retry (same interaction isolation as Modal 2).
- On success: stores parsed step strings on `self._wizard_view.instructions`, then calls `self._wizard_view.finalize(interaction)` to save everything.

Constructor receives a reference to the `AddRecipeWizardView` instance. No `session_factory` or `recipe_id` directly.

### `AddRecipeWizardView` (View — the glue)

Holds all accumulated state across the three modal steps:
- `session_factory` (callable)
- `guild_id`, `guild_name`, `user_id` (from the original interaction)
- `metadata` dict — populated after Modal 1
- `ingredients` list — populated after Modal 2 (parsed `ParsedIngredient` objects from `parsers.py`)
- `instructions` list — populated after Modal 3 (parsed step strings)

Timeout: 600 seconds (10 minutes).

**Button states:**
The view transitions through two button states:
1. After Modal 1: single button "Next: Add Ingredients" → on click, sends `WizardIngredientsModal`
2. After Modal 2: single button "Next: Add Instructions" → on click, sends `WizardInstructionsModal`

Each button state is a new view instance sent with the step-complete ephemeral message.

**`finalize(interaction)` method (called after Modal 3 succeeds):**
```python
async def finalize(self, interaction):
    with self.session_factory() as session:
        upsert_guild(session, guild_id, guild_name)
        now = datetime.now(timezone.utc)
        recipe = Recipe(
            guild_id=guild_id, name=metadata["name"],
            description=metadata["description"], servings=metadata["servings"],
            prep_time=metadata["prep_time"], cook_time=metadata["cook_time"],
            created_by=str(user_id), created_at=now, updated_at=now,
        )
        session.add(recipe)
        session.flush()  # get recipe.id for FK
        for item in self.ingredients:
            session.add(Ingredient(
                recipe_id=recipe.id, name=item.name,
                quantity=item.quantity, unit=item.unit, category=item.category,
            ))
        for i, step in enumerate(self.instructions, start=1):
            session.add(Instruction(
                recipe_id=recipe.id, step_number=i, instruction_text=step,
            ))
        session.flush()  # ensure relationships are populated before building embed
        session.refresh(recipe)  # reload with ingredients/instructions collections
        embed = RecipesCog._build_recipe_embed(recipe)
        session.commit()
    await interaction.response.send_message(embed=embed)
```
The `session.flush()` + `session.refresh(recipe)` ensures `recipe.ingredients` and `recipe.instructions` relationship collections are populated before `_build_recipe_embed` accesses them. The embed is built inside the session block, then sent after commit.

## Error Handling

| Scenario | Behavior |
|---|---|
| Validation error in Modal 1 (bad servings/times) | Ephemeral error message. Flow ends. User re-runs `/recipebot add`. |
| Parse error in Modal 2 (bad ingredient format) | Ephemeral error with line details. Step does NOT advance. User can click the "Next: Add Ingredients" button again to retry. |
| Empty/invalid input in Modal 3 | Ephemeral error. Step does NOT advance. User can click "Next: Add Instructions" button again to retry. |
| User dismisses a modal (clicks away / ESC) | Discord fires no event. View eventually times out. Nothing saved. |
| View timeout (10 minutes) | Buttons go dead. Nothing saved. |
| DB error on final save | Ephemeral error message. Transaction rolled back. Nothing saved. |

## Changes to Existing Code

### Modified: `/recipebot add` command (`RecipesCog.add`)

Currently creates `AddRecipeModal(self.bot.session_factory)` and sends it.

New behavior: creates `AddRecipeWizardModal` (no session_factory), paired with an `AddRecipeWizardView` that holds the session_factory and interaction context. Sends the modal.

### Unchanged

- `AddRecipeModal` class — kept in codebase, no longer used by the `add` command
- `IngredientsModal` class — still used by `/recipebot ingredients`
- `InstructionsModal` class — still used by `/recipebot instructions`
- `EditRecipeModal`, `DeleteConfirmView`, `TagModal`, `SearchPaginationView` — unchanged
- All other commands (`edit`, `delete`, `view`, `search`, `ingredients`, `instructions`, `tag`) — unchanged
- `parsers.py` — unchanged, reused by wizard modals
- `db/models.py` — unchanged
- `_build_recipe_embed` — unchanged, reused for final summary

## Summary Embed

The final message uses `RecipesCog._build_recipe_embed()` to render a complete recipe card: name, description, servings, prep/cook times, tags (none for a new recipe), ingredients, and instructions. This message is **public** (visible to the whole channel). All intermediate step-complete messages are **ephemeral**.

## Testing

Tests should cover:
- Happy path: all three modals completed successfully → recipe + ingredients + instructions in DB, summary embed sent
- Validation error in Modal 1 → error message, nothing saved
- Parse error in Modal 2 → error message, step doesn't advance
- Empty instructions in Modal 3 → error message, step doesn't advance
- All-or-nothing: if Modal 3 is never completed, no recipe exists in DB

Tests follow existing patterns in `tests/conftest.py` using `mock_interaction` and `make_session_factory`.
