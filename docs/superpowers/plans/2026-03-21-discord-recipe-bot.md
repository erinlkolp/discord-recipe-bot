# Discord Recipe Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Discord bot that manages per-server recipes, meal plans, and shopping lists, deployed via Docker Compose with Percona Server and Liquibase migrations.

**Architecture:** Three-container Docker Compose stack (percona → liquibase → recipebot). The bot is written in Python using discord.py with SQLAlchemy ORM. Business logic is split between pure functions (parsers, aggregation) and Discord cog classes, keeping testable code separate from Discord interaction handling.

**Tech Stack:** Python 3.12, discord.py 2.3+, SQLAlchemy 2.0+, PyMySQL, Liquibase (XML changelogs), Percona Server (MySQL-compatible), pytest + pytest-asyncio

---

## File Map

| File | Responsibility |
|---|---|
| `Dockerfile` | Bot container image |
| `docker-compose.yml` | Three-service stack definition |
| `.env.example` | Environment variable template |
| `requirements.txt` | Python dependencies |
| `liquibase/changelog.xml` | Liquibase master changelog |
| `liquibase/changes/0001-initial-schema.xml` | All table DDL |
| `recipebot/bot.py` | Entry point: loads env, creates engine, registers cogs, starts bot |
| `recipebot/db/connection.py` | SQLAlchemy engine factory, session factory, guild upsert helper |
| `recipebot/db/models.py` | All ORM model classes |
| `recipebot/parsers.py` | Pure functions: parse ingredient lines, parse instruction lines, aggregate shopping list |
| `recipebot/cogs/recipes.py` | All recipe commands: add, edit, delete, view, search, ingredients, instructions, tag |
| `recipebot/cogs/meal_plan.py` | Meal plan commands: plan add, plan view |
| `recipebot/cogs/shopping.py` | Shopping commands: shopping generate, shopping view |
| `tests/conftest.py` | Shared fixtures: in-memory SQLite engine, session, mock Discord interaction |
| `tests/test_models.py` | ORM model CRUD and constraint tests |
| `tests/test_parsers.py` | Ingredient parser, instruction parser, shopping aggregation tests |
| `tests/test_recipes.py` | Recipe cog command tests (mocked interaction) |
| `tests/test_meal_plan.py` | Meal plan cog command tests |
| `tests/test_shopping.py` | Shopping cog command tests |

---

### Task 1: Project Scaffold

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `recipebot/__init__.py`
- Create: `recipebot/cogs/__init__.py`
- Create: `recipebot/db/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p recipebot/cogs recipebot/db liquibase/changes tests
touch recipebot/__init__.py recipebot/cogs/__init__.py recipebot/db/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write `requirements.txt`**

```
discord.py>=2.3.2
SQLAlchemy>=2.0.30
PyMySQL>=1.1.1
cryptography>=42.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.6
```

- [ ] **Step 3: Write `.env.example`**

```
DISCORD_BOT_TOKEN=
DB_HOST=percona
DB_PORT=3306
DB_NAME=recipebot
DB_USER=recipebot
DB_PASSWORD=
DB_ROOT_PASSWORD=
```

- [ ] **Step 4: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY recipebot/ ./recipebot/
CMD ["python", "recipebot/bot.py"]
```

- [ ] **Step 5: Write `docker-compose.yml`**

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

- [ ] **Step 6: Write `tests/conftest.py`**

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from recipebot.db.models import Base


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def mock_interaction():
    interaction = MagicMock()
    interaction.guild_id = 123456789
    interaction.guild.name = "Test Guild"
    interaction.guild.id = 123456789
    interaction.user.id = 987654321
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_session_factory(session):
    """Return a callable that acts as a context manager yielding the given session.
    Use this in bot fixtures so `with self.bot.session_factory() as s:` works in tests."""
    from contextlib import contextmanager

    @contextmanager
    def factory():
        yield session

    return factory
```

- [ ] **Step 7: Install dependencies locally**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 8: Verify tests run (empty suite)**

```bash
pytest tests/ -v
```

Expected: `no tests ran` or `0 passed`.

- [ ] **Step 9: Commit**

```bash
git add .
git commit -m "feat: project scaffold"
```

---

### Task 2: Liquibase Migrations

**Files:**
- Create: `liquibase/changelog.xml`
- Create: `liquibase/changes/0001-initial-schema.xml`

- [ ] **Step 1: Write `liquibase/changelog.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <include file="changes/0001-initial-schema.xml" relativeToChangelogFile="true"/>
</databaseChangeLog>
```

- [ ] **Step 2: Write `liquibase/changes/0001-initial-schema.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <changeSet id="0001-guilds" author="recipebot">
        <createTable tableName="guilds">
            <column name="guild_id" type="VARCHAR(20)">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="name" type="VARCHAR(100)"/>
        </createTable>
    </changeSet>

    <changeSet id="0001-recipes" author="recipebot">
        <createTable tableName="recipes">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="guild_id" type="VARCHAR(20)">
                <constraints nullable="false" foreignKeyName="fk_recipe_guild"
                    references="guilds(guild_id)"/>
            </column>
            <column name="name" type="VARCHAR(200)">
                <constraints nullable="false"/>
            </column>
            <column name="description" type="TEXT"/>
            <column name="servings" type="INT">
                <constraints nullable="false"/>
            </column>
            <column name="prep_time" type="INT"/>
            <column name="cook_time" type="INT"/>
            <column name="created_by" type="VARCHAR(20)"/>
            <column name="created_at" type="DATETIME"/>
            <column name="updated_at" type="DATETIME"/>
        </createTable>
        <addCheckConstraint tableName="recipes" constraintName="ck_recipe_servings"
            checkCondition="servings > 0"/>
        <createIndex tableName="recipes" indexName="idx_recipe_guild_id">
            <column name="guild_id"/>
        </createIndex>
    </changeSet>

    <changeSet id="0001-ingredients" author="recipebot">
        <createTable tableName="ingredients">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="recipe_id" type="INT">
                <constraints nullable="false" foreignKeyName="fk_ingredient_recipe"
                    references="recipes(id)" deleteCascade="true"/>
            </column>
            <column name="name" type="VARCHAR(200)">
                <constraints nullable="false"/>
            </column>
            <column name="quantity" type="DECIMAL(10,3)"/>
            <column name="unit" type="VARCHAR(50)"/>
            <column name="category" type="ENUM('produce','dairy','meat','seafood','pantry','frozen','bakery','other')"
                defaultValue="other">
                <constraints nullable="false"/>
            </column>
        </createTable>
    </changeSet>

    <changeSet id="0001-instructions" author="recipebot">
        <createTable tableName="instructions">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="recipe_id" type="INT">
                <constraints nullable="false" foreignKeyName="fk_instruction_recipe"
                    references="recipes(id)" deleteCascade="true"/>
            </column>
            <column name="step_number" type="INT">
                <constraints nullable="false"/>
            </column>
            <column name="instruction_text" type="TEXT">
                <constraints nullable="false"/>
            </column>
        </createTable>
    </changeSet>

    <changeSet id="0001-tags" author="recipebot">
        <createTable tableName="tags">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="recipe_id" type="INT">
                <constraints nullable="false" foreignKeyName="fk_tag_recipe"
                    references="recipes(id)" deleteCascade="true"/>
            </column>
            <column name="tag_name" type="VARCHAR(100)">
                <constraints nullable="false"/>
            </column>
        </createTable>
    </changeSet>

    <changeSet id="0001-meal_plans" author="recipebot">
        <createTable tableName="meal_plans">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="guild_id" type="VARCHAR(20)">
                <constraints nullable="false" foreignKeyName="fk_meal_plan_guild"
                    references="guilds(guild_id)"/>
            </column>
            <column name="week_start_date" type="DATE">
                <constraints nullable="false"/>
            </column>
            <column name="created_by" type="VARCHAR(20)"/>
        </createTable>
        <addUniqueConstraint tableName="meal_plans" columnNames="guild_id,week_start_date"
            constraintName="uq_meal_plan_guild_week"/>
    </changeSet>

    <changeSet id="0001-meal_plan_entries" author="recipebot">
        <createTable tableName="meal_plan_entries">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="meal_plan_id" type="INT">
                <constraints nullable="false" foreignKeyName="fk_entry_meal_plan"
                    references="meal_plans(id)" deleteCascade="true"/>
            </column>
            <column name="recipe_id" type="INT">
                <constraints nullable="false" foreignKeyName="fk_entry_recipe"
                    references="recipes(id)" deleteCascade="true"/>
            </column>
            <column name="day_of_week" type="ENUM('monday','tuesday','wednesday','thursday','friday','saturday','sunday')">
                <constraints nullable="false"/>
            </column>
            <column name="meal_type" type="ENUM('breakfast','lunch','dinner','snack')">
                <constraints nullable="false"/>
            </column>
            <column name="servings" type="INT">
                <constraints nullable="false"/>
            </column>
        </createTable>
        <addUniqueConstraint tableName="meal_plan_entries"
            columnNames="meal_plan_id,day_of_week,meal_type,recipe_id"
            constraintName="uq_meal_plan_entry"/>
        <addCheckConstraint tableName="meal_plan_entries" constraintName="ck_entry_servings"
            checkCondition="servings > 0"/>
    </changeSet>

    <changeSet id="0001-shopping_lists" author="recipebot">
        <createTable tableName="shopping_lists">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="guild_id" type="VARCHAR(20)">
                <constraints nullable="false" foreignKeyName="fk_shopping_list_guild"
                    references="guilds(guild_id)"/>
            </column>
            <column name="meal_plan_id" type="INT">
                <constraints foreignKeyName="fk_shopping_list_meal_plan"
                    references="meal_plans(id)" deleteCascade="true"/>
            </column>
            <column name="generated_at" type="DATETIME"/>
        </createTable>
    </changeSet>

    <changeSet id="0001-shopping_list_items" author="recipebot">
        <createTable tableName="shopping_list_items">
            <column name="id" type="INT" autoIncrement="true">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="shopping_list_id" type="INT">
                <constraints nullable="false" foreignKeyName="fk_item_shopping_list"
                    references="shopping_lists(id)" deleteCascade="true"/>
            </column>
            <column name="ingredient_name" type="VARCHAR(200)">
                <constraints nullable="false"/>
            </column>
            <column name="total_quantity" type="DECIMAL(10,3)"/>
            <column name="unit" type="VARCHAR(50)"/>
            <column name="category" type="ENUM('produce','dairy','meat','seafood','pantry','frozen','bakery','other')"
                defaultValue="other">
                <constraints nullable="false"/>
            </column>
        </createTable>
    </changeSet>

</databaseChangeLog>
```

- [ ] **Step 3: Commit**

```bash
git add liquibase/
git commit -m "feat: add Liquibase initial schema migration"
```

---

### Task 3: DB Layer — Models and Connection

**Files:**
- Create: `recipebot/db/connection.py`
- Create: `recipebot/db/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for models in `tests/test_models.py`**

```python
from datetime import date
from recipebot.db.models import Guild, Recipe, Ingredient, Instruction, Tag, MealPlan, MealPlanEntry, ShoppingList, ShoppingListItem


def test_create_guild(session):
    guild = Guild(guild_id="111", name="Test Server")
    session.add(guild)
    session.commit()
    result = session.get(Guild, "111")
    assert result.name == "Test Server"


def test_create_recipe(session):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    assert recipe.id is not None
    assert recipe.name == "Pasta"


def test_recipe_cascade_deletes_ingredients(session):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    ing = Ingredient(recipe_id=recipe.id, name="flour", category="pantry")
    session.add(ing)
    session.commit()
    ing_id = ing.id
    session.delete(recipe)
    session.commit()
    assert session.get(Ingredient, ing_id) is None


def test_meal_plan_unique_constraint(session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    mp1 = MealPlan(guild_id="111", week_start_date=date(2026, 3, 16))
    mp2 = MealPlan(guild_id="111", week_start_date=date(2026, 3, 16))
    session.add(mp1)
    session.commit()
    session.add(mp2)
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_models.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — models don't exist yet.

- [ ] **Step 3: Write `recipebot/db/models.py`**

```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Date, DateTime,
    Enum, ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


CATEGORY_ENUM = Enum(
    'produce', 'dairy', 'meat', 'seafood', 'pantry', 'frozen', 'bakery', 'other',
    name='category_enum'
)
DAY_ENUM = Enum(
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    name='day_enum'
)
MEAL_TYPE_ENUM = Enum('breakfast', 'lunch', 'dinner', 'snack', name='meal_type_enum')


class Guild(Base):
    __tablename__ = 'guilds'
    guild_id = Column(String(20), primary_key=True)
    name = Column(String(100))


class Recipe(Base):
    __tablename__ = 'recipes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(20), ForeignKey('guilds.guild_id'), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    servings = Column(Integer, nullable=False)
    prep_time = Column(Integer)
    cook_time = Column(Integer)
    created_by = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ingredients = relationship('Ingredient', back_populates='recipe', cascade='all, delete-orphan')
    instructions = relationship(
        'Instruction', back_populates='recipe', cascade='all, delete-orphan',
        order_by='Instruction.step_number'
    )
    tags = relationship('Tag', back_populates='recipe', cascade='all, delete-orphan')
    __table_args__ = (CheckConstraint('servings > 0', name='ck_recipe_servings'),)


class Ingredient(Base):
    __tablename__ = 'ingredients'
    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(200), nullable=False)
    quantity = Column(Numeric(10, 3))
    unit = Column(String(50))
    category = Column(CATEGORY_ENUM, nullable=False, default='other')
    recipe = relationship('Recipe', back_populates='ingredients')


class Instruction(Base):
    __tablename__ = 'instructions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    step_number = Column(Integer, nullable=False)
    instruction_text = Column(Text, nullable=False)
    recipe = relationship('Recipe', back_populates='instructions')


class Tag(Base):
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    tag_name = Column(String(100), nullable=False)
    recipe = relationship('Recipe', back_populates='tags')


class MealPlan(Base):
    __tablename__ = 'meal_plans'
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(20), ForeignKey('guilds.guild_id'), nullable=False)
    week_start_date = Column(Date, nullable=False)
    created_by = Column(String(20))
    entries = relationship('MealPlanEntry', back_populates='meal_plan', cascade='all, delete-orphan')
    __table_args__ = (
        UniqueConstraint('guild_id', 'week_start_date', name='uq_meal_plan_guild_week'),
    )


class MealPlanEntry(Base):
    __tablename__ = 'meal_plan_entries'
    id = Column(Integer, primary_key=True, autoincrement=True)
    meal_plan_id = Column(Integer, ForeignKey('meal_plans.id', ondelete='CASCADE'), nullable=False)
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    day_of_week = Column(DAY_ENUM, nullable=False)
    meal_type = Column(MEAL_TYPE_ENUM, nullable=False)
    servings = Column(Integer, nullable=False)
    meal_plan = relationship('MealPlan', back_populates='entries')
    recipe = relationship('Recipe')
    __table_args__ = (
        UniqueConstraint('meal_plan_id', 'day_of_week', 'meal_type', 'recipe_id',
                         name='uq_meal_plan_entry'),
        CheckConstraint('servings > 0', name='ck_entry_servings'),
    )


class ShoppingList(Base):
    __tablename__ = 'shopping_lists'
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(20), ForeignKey('guilds.guild_id'), nullable=False)
    meal_plan_id = Column(Integer, ForeignKey('meal_plans.id', ondelete='CASCADE'))
    generated_at = Column(DateTime, default=datetime.utcnow)
    items = relationship('ShoppingListItem', back_populates='shopping_list',
                         cascade='all, delete-orphan')


class ShoppingListItem(Base):
    __tablename__ = 'shopping_list_items'
    id = Column(Integer, primary_key=True, autoincrement=True)
    shopping_list_id = Column(Integer, ForeignKey('shopping_lists.id', ondelete='CASCADE'),
                              nullable=False)
    ingredient_name = Column(String(200), nullable=False)
    total_quantity = Column(Numeric(10, 3))
    unit = Column(String(50))
    category = Column(CATEGORY_ENUM, nullable=False, default='other')
    shopping_list = relationship('ShoppingList', back_populates='items')
```

- [ ] **Step 4: Write `recipebot/db/connection.py`**

```python
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session


def create_db_engine():
    url = (
        f"mysql+pymysql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    )
    return create_engine(url, pool_pre_ping=True)


def get_session_factory(engine):
    return sessionmaker(bind=engine)


def upsert_guild(session: Session, guild_id: str, guild_name: str) -> None:
    """Ensure a guild row exists; safe to call on every command invocation."""
    session.execute(
        text(
            "INSERT INTO guilds (guild_id, name) VALUES (:id, :name) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name)"
        ),
        {"id": str(guild_id), "name": guild_name},
    )
    session.commit()


def current_week_start():
    """Return the Monday of the current ISO calendar week."""
    from datetime import date, timedelta
    today = date.today()
    return today - timedelta(days=today.weekday())
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_models.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add recipebot/db/ tests/test_models.py
git commit -m "feat: add ORM models and DB connection module"
```

---

### Task 4: Parsers

**Files:**
- Create: `recipebot/parsers.py`
- Create: `tests/test_parsers.py`

- [ ] **Step 1: Write failing tests in `tests/test_parsers.py`**

```python
from decimal import Decimal
from recipebot.parsers import parse_ingredients, parse_instructions, aggregate_shopping_items


def test_parse_ingredients_valid():
    text = "flour, 2, cup, pantry\nsalt, 1, tsp, pantry"
    items, errors = parse_ingredients(text)
    assert len(errors) == 0
    assert len(items) == 2
    assert items[0].name == "flour"
    assert items[0].quantity == Decimal("2")
    assert items[0].unit == "cup"
    assert items[0].category == "pantry"


def test_parse_ingredients_case_insensitive_category():
    text = "milk, 1, cup, DAIRY"
    items, errors = parse_ingredients(text)
    assert len(errors) == 0
    assert items[0].category == "dairy"


def test_parse_ingredients_wrong_field_count():
    text = "flour, 2, cup"
    items, errors = parse_ingredients(text)
    assert len(items) == 0
    assert len(errors) == 1
    assert errors[0].line_number == 1


def test_parse_ingredients_invalid_quantity():
    text = "flour, abc, cup, pantry"
    items, errors = parse_ingredients(text)
    assert len(errors) == 1
    assert "abc" in errors[0].reason


def test_parse_ingredients_invalid_category():
    text = "flour, 2, cup, snacks"
    items, errors = parse_ingredients(text)
    assert len(errors) == 1
    assert "snacks" in errors[0].reason


def test_parse_ingredients_skips_blank_lines():
    text = "flour, 2, cup, pantry\n\nsalt, 1, tsp, pantry"
    items, errors = parse_ingredients(text)
    assert len(items) == 2
    assert len(errors) == 0


def test_parse_instructions_basic():
    steps = parse_instructions("Boil water\nAdd pasta\nDrain")
    assert steps == ["Boil water", "Add pasta", "Drain"]


def test_parse_instructions_skips_blanks():
    steps = parse_instructions("Step one\n\nStep two")
    assert steps == ["Step one", "Step two"]


def test_aggregate_shopping_items_sums_same_unit():
    items = [
        {"name": "flour", "quantity": Decimal("2"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
        {"name": "flour", "quantity": Decimal("1"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert len(result) == 1
    assert result[0]["total_quantity"] == Decimal("3")


def test_aggregate_shopping_items_scales_by_servings():
    items = [
        {"name": "flour", "quantity": Decimal("2"), "unit": "cup", "category": "pantry",
         "entry_servings": 8, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert result[0]["total_quantity"] == Decimal("4")


def test_aggregate_shopping_items_different_units_separate():
    items = [
        {"name": "flour", "quantity": Decimal("2"), "unit": "cup", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
        {"name": "flour", "quantity": Decimal("100"), "unit": "g", "category": "pantry",
         "entry_servings": 4, "recipe_servings": 4},
    ]
    result = aggregate_shopping_items(items)
    assert len(result) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parsers.py -v
```

Expected: `ImportError` — parsers module doesn't exist yet.

- [ ] **Step 3: Write `recipebot/parsers.py`**

```python
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from typing import Optional

VALID_CATEGORIES = {'produce', 'dairy', 'meat', 'seafood', 'pantry', 'frozen', 'bakery', 'other'}


@dataclass
class ParsedIngredient:
    name: str
    quantity: Optional[Decimal]
    unit: str
    category: str


@dataclass
class ParseError:
    line_number: int
    line: str
    reason: str


def parse_ingredients(text: str) -> tuple[list[ParsedIngredient], list[ParseError]]:
    """Parse ingredient text. Format per line: name, quantity, unit, category.
    Blank lines are silently skipped. Returns (ingredients, errors).
    On any error the whole submission should be rejected — errors list will be non-empty."""
    ingredients: list[ParsedIngredient] = []
    errors: list[ParseError] = []
    for i, raw_line in enumerate(text.strip().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 4:
            errors.append(ParseError(i, raw_line,
                f"Expected 4 comma-separated fields, got {len(parts)}"))
            continue
        name, qty_str, unit, cat_str = parts
        if not name:
            errors.append(ParseError(i, raw_line, "Name cannot be empty"))
            continue
        category = cat_str.lower()
        if category not in VALID_CATEGORIES:
            errors.append(ParseError(i, raw_line,
                f"Invalid category '{cat_str}'. Valid values: {', '.join(sorted(VALID_CATEGORIES))}"))
            continue
        try:
            quantity = Decimal(qty_str) if qty_str else None
        except InvalidOperation:
            errors.append(ParseError(i, raw_line, f"Invalid quantity '{qty_str}' — must be a number"))
            continue
        ingredients.append(ParsedIngredient(name=name, quantity=quantity, unit=unit, category=category))
    return ingredients, errors


def parse_instructions(text: str) -> list[str]:
    """Parse instruction text. One step per line, blank lines skipped.
    Returned list index + 1 = step_number."""
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def aggregate_shopping_items(items: list[dict]) -> list[dict]:
    """Aggregate and scale ingredient quantities for a shopping list.

    Each item dict must have keys:
        name, quantity (Decimal|None), unit, category,
        entry_servings (int), recipe_servings (int)

    Returns list of dicts with keys: ingredient_name, total_quantity, unit, category.
    Items with the same (name.lower(), unit) are summed after scaling.
    Different units for the same ingredient produce separate line items.
    """
    totals: dict[tuple, Decimal] = defaultdict(Decimal)
    categories: dict[tuple, str] = {}

    seen_keys: set = set()
    for item in items:
        scale = Decimal(str(item['entry_servings'])) / Decimal(str(item['recipe_servings']))
        key = (item['name'].lower(), item['unit'] or '')
        seen_keys.add(key)
        if item['quantity'] is not None:
            totals[key] += item['quantity'] * scale
        categories[key] = item['category']

    return [
        {
            'ingredient_name': key[0],
            'unit': key[1],
            'total_quantity': totals[key] if totals[key] else None,
            'category': categories[key],
        }
        for key in seen_keys
    ]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_parsers.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add recipebot/parsers.py tests/test_parsers.py
git commit -m "feat: add ingredient/instruction parsers and shopping aggregation"
```

---

### Task 5: Bot Entry Point

**Files:**
- Create: `recipebot/bot.py`

- [ ] **Step 1: Write `recipebot/bot.py`**

```python
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
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from recipebot.bot import RecipeBot; print('OK')"
```

Expected: `OK` (will fail if cog files don't exist yet — create stub files to unblock this).

- [ ] **Step 3: Create stub cog files**

```bash
# recipebot/cogs/recipes.py
cat > recipebot/cogs/recipes.py << 'EOF'
from discord.ext import commands
class RecipesCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
async def setup(bot): await bot.add_cog(RecipesCog(bot))
EOF

# recipebot/cogs/meal_plan.py
cat > recipebot/cogs/meal_plan.py << 'EOF'
from discord.ext import commands
class MealPlanCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
async def setup(bot): await bot.add_cog(MealPlanCog(bot))
EOF

# recipebot/cogs/shopping.py
cat > recipebot/cogs/shopping.py << 'EOF'
from discord.ext import commands
class ShoppingCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
async def setup(bot): await bot.add_cog(ShoppingCog(bot))
EOF
```

- [ ] **Step 4: Verify import works**

```bash
python -c "from recipebot.bot import RecipeBot; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add recipebot/bot.py recipebot/cogs/
git commit -m "feat: add bot entry point and stub cogs"
```

---

### Task 6: Recipe Cog — add, edit, delete

**Files:**
- Modify: `recipebot/cogs/recipes.py` (replace stub)
- Create: `tests/test_recipes.py`

**discord.py concepts for this task:**
- `app_commands.Group` — creates a `/recipebot` command group
- `discord.ui.Modal` — popup form with `TextInput` fields (max 5)
- `discord.ui.View` with buttons — for delete confirmation
- `interaction.response.send_modal(modal)` — opens modal
- `interaction.response.send_message(ephemeral=True)` — private response
- Autocomplete: decorated with `@app_commands.autocomplete(param=fn)`; fn returns `list[app_commands.Choice]`

- [ ] **Step 1: Write failing tests in `tests/test_recipes.py`**

```python
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from recipebot.db.models import Guild, Recipe
from recipebot.cogs.recipes import RecipesCog, AddRecipeModal


@pytest.fixture
def bot(session):
    from tests.conftest import make_session_factory
    b = MagicMock()
    b.session_factory = make_session_factory(session)
    return b


@pytest.mark.asyncio
async def test_add_recipe_modal_creates_recipe(session, bot, mock_interaction):
    mock_interaction.guild_id = 111
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = 999
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()

    modal = AddRecipeModal(session)
    modal.name.default = "Spaghetti"
    modal.description.default = "Classic pasta"
    modal.servings.default = "4"
    modal.prep_time.default = "10"
    modal.cook_time.default = "20"

    # Simulate on_submit
    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    recipe = session.query(Recipe).filter_by(guild_id="111", name="Spaghetti").first()
    assert recipe is not None
    assert recipe.servings == 4


@pytest.mark.asyncio
async def test_delete_recipe_missing(session, bot, mock_interaction):
    cog = RecipesCog(bot)
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    await cog.delete.callback(cog, mock_interaction, "Nonexistent")
    mock_interaction.response.send_message.assert_called_once()
    args, kwargs = mock_interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_recipes.py -v
```

Expected: `ImportError` — `AddRecipeModal` not defined yet.

- [ ] **Step 3: Implement `recipebot/cogs/recipes.py` (add/edit/delete)**

```python
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session
from datetime import datetime
from recipebot.db.models import Recipe, Guild
from recipebot.db.connection import upsert_guild


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=discord.Color.red())


def success_embed(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=discord.Color.green())


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
        try:
            servings = int(self.servings.value)
            if servings <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Servings must be a positive whole number."), ephemeral=True
            )
            return

        prep = int(self.prep_time.value) if self.prep_time.value.strip() else None
        cook = int(self.cook_time.value) if self.cook_time.value.strip() else None

        upsert_guild(self._session, str(interaction.guild_id), interaction.guild.name)
        recipe = Recipe(
            guild_id=str(interaction.guild_id),
            name=self.name.value.strip(),
            description=self.description.value.strip() or None,
            servings=servings,
            prep_time=prep,
            cook_time=cook,
            created_by=str(interaction.user.id),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
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
        try:
            servings = int(self.servings.value)
            if servings <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Servings must be a positive whole number."), ephemeral=True
            )
            return
        self._recipe.name = self.name.value.strip()
        self._recipe.description = self.description.value.strip() or None
        self._recipe.servings = servings
        self._recipe.prep_time = int(self.prep_time.value) if self.prep_time.value.strip() else None
        self._recipe.cook_time = int(self.cook_time.value) if self.cook_time.value.strip() else None
        self._recipe.updated_at = datetime.utcnow()
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_recipes.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: add recipe add/edit/delete commands"
```

---

### Task 7: Recipe Cog — view and search

**Files:**
- Modify: `recipebot/cogs/recipes.py`
- Modify: `tests/test_recipes.py`

- [ ] **Step 1: Add failing tests**

Add to `tests/test_recipes.py`:

```python
@pytest.mark.asyncio
async def test_view_recipe_sends_embed(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4, created_at=datetime.utcnow())
    session.add(recipe)
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = RecipesCog(bot)
    await cog.view.callback(cog, mock_interaction, "Pasta")
    mock_interaction.response.send_message.assert_called_once()
    call_kwargs = mock_interaction.response.send_message.call_args[1]
    assert "embed" in call_kwargs


@pytest.mark.asyncio
async def test_view_recipe_not_found(session, bot, mock_interaction):
    mock_interaction.guild_id = "111"
    cog = RecipesCog(bot)
    await cog.view.callback(cog, mock_interaction, "Ghost Recipe")
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_recipes.py::test_view_recipe_sends_embed -v
```

Expected: `AttributeError` — `view` command not defined.

- [ ] **Step 3: Add view and search commands to `recipebot/cogs/recipes.py`**

Add these methods to `RecipesCog`:

```python
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
```

Also add `SearchPaginationView` class before `RecipesCog`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_recipes.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: add recipe view and search commands"
```

---

### Task 8: Recipe Cog — ingredients, instructions, tags

**Files:**
- Modify: `recipebot/cogs/recipes.py`
- Modify: `tests/test_recipes.py`

- [ ] **Step 1: Add failing tests**

Add to `tests/test_recipes.py`:

```python
from recipebot.db.models import Ingredient, Instruction, Tag

@pytest.mark.asyncio
async def test_ingredients_command_replaces(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    recipe = Recipe(guild_id="111", name="Pasta", servings=4, created_at=datetime.utcnow())
    session.add(recipe)
    session.commit()
    old_ing = Ingredient(recipe_id=recipe.id, name="old", category="other")
    session.add(old_ing)
    session.commit()

    from recipebot.cogs.recipes import IngredientsModal
    modal = IngredientsModal(session, recipe)
    modal.ingredients_text.default = "flour, 2, cup, pantry\nsalt, 1, tsp, pantry"
    mock_interaction.guild_id = "111"
    await modal.on_submit(mock_interaction)

    remaining = session.query(Ingredient).filter_by(recipe_id=recipe.id).all()
    assert len(remaining) == 2
    assert remaining[0].name == "flour"


@pytest.mark.asyncio
async def test_ingredients_command_rejects_bad_lines(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    recipe = Recipe(guild_id="111", name="Pasta", servings=4, created_at=datetime.utcnow())
    session.add(recipe)
    session.commit()

    from recipebot.cogs.recipes import IngredientsModal
    modal = IngredientsModal(session, recipe)
    modal.ingredients_text.default = "flour, 2, cup"  # missing category
    await modal.on_submit(mock_interaction)

    mock_interaction.response.send_message.assert_called_once()
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True
    remaining = session.query(Ingredient).filter_by(recipe_id=recipe.id).all()
    assert len(remaining) == 0  # no partial writes
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_recipes.py::test_ingredients_command_replaces -v
```

Expected: `ImportError` — `IngredientsModal` not defined.

- [ ] **Step 3: Add ingredients, instructions, and tag commands to `recipebot/cogs/recipes.py`**

Add modals:

```python
class IngredientsModal(discord.ui.Modal, title="Set Ingredients"):
    ingredients_text = discord.ui.TextInput(
        label="Ingredients (name, qty, unit, category per line)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
        placeholder="flour, 2, cup, pantry\neggs, 3, , dairy",
    )

    def __init__(self, session: Session, recipe: Recipe):
        super().__init__()
        self._session = session
        self._recipe = recipe

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.parsers import parse_ingredients
        from recipebot.db.models import Ingredient
        items, errors = parse_ingredients(self.ingredients_text.value)
        if errors:
            lines = "\n".join(f"Line {e.line_number}: {e.reason}" for e in errors)
            await interaction.response.send_message(
                embed=error_embed(f"Fix these errors and resubmit:\n```{lines}```"),
                ephemeral=True,
            )
            return
        self._session.query(Ingredient).filter_by(recipe_id=self._recipe.id).delete()
        for item in items:
            self._session.add(Ingredient(
                recipe_id=self._recipe.id,
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                category=item.category,
            ))
        self._session.commit()
        await interaction.response.send_message(
            embed=success_embed(f"Ingredients updated for **{self._recipe.name}**."),
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

    def __init__(self, session: Session, recipe: Recipe):
        super().__init__()
        self._session = session
        self._recipe = recipe

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.parsers import parse_instructions
        from recipebot.db.models import Instruction
        steps = parse_instructions(self.instructions_text.value)
        if not steps:
            await interaction.response.send_message(
                embed=error_embed("No instructions provided."), ephemeral=True
            )
            return
        self._session.query(Instruction).filter_by(recipe_id=self._recipe.id).delete()
        for i, text in enumerate(steps, start=1):
            self._session.add(Instruction(
                recipe_id=self._recipe.id, step_number=i, instruction_text=text
            ))
        self._session.commit()
        await interaction.response.send_message(
            embed=success_embed(f"Instructions updated for **{self._recipe.name}**."),
            ephemeral=True,
        )


class TagModal(discord.ui.Modal, title="Set Tags"):
    tags_text = discord.ui.TextInput(
        label="Tags (comma-separated)",
        required=False,
        max_length=500,
        placeholder="italian, pasta, dinner",
    )

    def __init__(self, session: Session, recipe: Recipe):
        super().__init__()
        self._session = session
        self._recipe = recipe
        self.tags_text.default = ", ".join(t.tag_name for t in recipe.tags)

    async def on_submit(self, interaction: discord.Interaction):
        from recipebot.db.models import Tag
        self._session.query(Tag).filter_by(recipe_id=self._recipe.id).delete()
        raw = self.tags_text.value.strip()
        if raw:
            for tag in {t.strip().lower() for t in raw.split(",") if t.strip()}:
                self._session.add(Tag(recipe_id=self._recipe.id, tag_name=tag))
        self._session.commit()
        await interaction.response.send_message(
            embed=success_embed(f"Tags updated for **{self._recipe.name}**."),
            ephemeral=True,
        )
```

Add commands to `RecipesCog`:

```python
    @recipebot_group.command(name="ingredients", description="Set ingredients for a recipe (replaces existing)")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def ingredients(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(embed=error_embed("Recipe not found."), ephemeral=True)
                return
            modal = IngredientsModal(session, r)
            await interaction.response.send_modal(modal)
            await modal.wait()

    @recipebot_group.command(name="instructions", description="Set instructions for a recipe (replaces existing)")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def instructions(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(embed=error_embed("Recipe not found."), ephemeral=True)
                return
            modal = InstructionsModal(session, r)
            await interaction.response.send_modal(modal)
            await modal.wait()

    @recipebot_group.command(name="tag", description="Set tags for a recipe")
    @app_commands.autocomplete(recipe=_recipe_autocomplete)
    async def tag(self, interaction: discord.Interaction, recipe: str):
        with self.bot.session_factory() as session:
            r = self._get_recipe(session, str(interaction.guild_id), recipe)
            if not r:
                await interaction.response.send_message(embed=error_embed("Recipe not found."), ephemeral=True)
                return
            modal = TagModal(session, r)
            await interaction.response.send_modal(modal)
            await modal.wait()
```

At the end of `recipes.py`, add the cog to the group:

```python
async def setup(bot):
    cog = RecipesCog(bot)
    bot.tree.add_command(recipebot_group)
    await bot.add_cog(cog)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_recipes.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add recipebot/cogs/recipes.py tests/test_recipes.py
git commit -m "feat: add ingredients, instructions, and tag commands"
```

---

### Task 9: Meal Plan Cog

**Files:**
- Modify: `recipebot/cogs/meal_plan.py` (replace stub)
- Create: `tests/test_meal_plan.py`

- [ ] **Step 1: Write failing tests in `tests/test_meal_plan.py`**

```python
import pytest
from datetime import date
from unittest.mock import MagicMock, AsyncMock, patch
from recipebot.db.models import Guild, Recipe, MealPlan, MealPlanEntry
from recipebot.cogs.meal_plan import MealPlanCog


@pytest.fixture
def bot(session):
    from tests.conftest import make_session_factory
    b = MagicMock()
    b.session_factory = make_session_factory(session)
    return b


@pytest.mark.asyncio
async def test_plan_add_creates_entry(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"

    cog = MealPlanCog(bot)
    with patch("recipebot.cogs.meal_plan.current_week_start", return_value=date(2026, 3, 16)):
        await cog.plan_add.callback(cog, mock_interaction, "Pasta", "monday", "dinner", 2)

    entry = session.query(MealPlanEntry).first()
    assert entry is not None
    assert entry.servings == 2
    assert entry.day_of_week == "monday"


@pytest.mark.asyncio
async def test_plan_add_rejects_duplicate(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    recipe = Recipe(guild_id="111", name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    mp = MealPlan(guild_id="111", week_start_date=date(2026, 3, 16))
    session.add(mp)
    session.commit()
    entry = MealPlanEntry(meal_plan_id=mp.id, recipe_id=recipe.id,
                          day_of_week="monday", meal_type="dinner", servings=2)
    session.add(entry)
    session.commit()

    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    mock_interaction.user.id = "999"
    cog = MealPlanCog(bot)
    with patch("recipebot.cogs.meal_plan.current_week_start", return_value=date(2026, 3, 16)):
        await cog.plan_add.callback(cog, mock_interaction, "Pasta", "monday", "dinner", 2)

    msg_kwargs = mock_interaction.response.send_message.call_args[1]
    assert msg_kwargs.get("ephemeral") is True
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_meal_plan.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `recipebot/cogs/meal_plan.py`**

```python
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from recipebot.db.models import Recipe, MealPlan, MealPlanEntry
from recipebot.db.connection import upsert_guild, current_week_start
from recipebot.cogs.recipes import recipebot_group, error_embed, success_embed

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack']


def _upsert_meal_plan(session: Session, guild_id: str, user_id: str) -> MealPlan:
    week = current_week_start()
    from sqlalchemy import text
    session.execute(
        text(
            "INSERT INTO meal_plans (guild_id, week_start_date, created_by) "
            "VALUES (:g, :w, :u) ON DUPLICATE KEY UPDATE created_by = VALUES(created_by)"
        ),
        {"g": guild_id, "w": week, "u": user_id},
    )
    session.commit()
    return session.query(MealPlan).filter_by(guild_id=guild_id, week_start_date=week).one()


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
            meal_plan = _upsert_meal_plan(session, guild_id, user_id)
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
            await interaction.response.send_message(
                embed=success_embed(
                    f"Added **{r.name}** to {day.capitalize()} {meal_type} "
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_meal_plan.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add recipebot/cogs/meal_plan.py tests/test_meal_plan.py
git commit -m "feat: add meal plan commands"
```

---

### Task 10: Shopping Cog

**Files:**
- Modify: `recipebot/cogs/shopping.py` (replace stub)
- Create: `tests/test_shopping.py`

- [ ] **Step 1: Write failing tests in `tests/test_shopping.py`**

```python
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from recipebot.db.models import Guild, Recipe, Ingredient, MealPlan, MealPlanEntry, ShoppingList, ShoppingListItem
from recipebot.cogs.shopping import ShoppingCog


@pytest.fixture
def bot(session):
    from tests.conftest import make_session_factory
    b = MagicMock()
    b.session_factory = make_session_factory(session)
    return b


def _seed_plan_with_recipe(session, guild_id="111"):
    session.add(Guild(guild_id=guild_id, name="Test"))
    session.commit()
    recipe = Recipe(guild_id=guild_id, name="Pasta", servings=4)
    session.add(recipe)
    session.commit()
    session.add(Ingredient(recipe_id=recipe.id, name="flour", quantity=Decimal("2"),
                           unit="cup", category="pantry"))
    session.commit()
    mp = MealPlan(guild_id=guild_id, week_start_date=date(2026, 3, 16))
    session.add(mp)
    session.commit()
    session.add(MealPlanEntry(meal_plan_id=mp.id, recipe_id=recipe.id,
                              day_of_week="monday", meal_type="dinner", servings=4))
    session.commit()
    return mp


@pytest.mark.asyncio
async def test_shopping_generate_creates_list(session, bot, mock_interaction):
    mp = _seed_plan_with_recipe(session)
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_generate.callback(cog, mock_interaction)
    sl = session.query(ShoppingList).filter_by(guild_id="111").first()
    assert sl is not None
    assert len(sl.items) == 1
    assert sl.items[0].ingredient_name == "flour"
    assert sl.items[0].total_quantity == Decimal("2.000")


@pytest.mark.asyncio
async def test_shopping_generate_replaces_existing(session, bot, mock_interaction):
    mp = _seed_plan_with_recipe(session)
    old_sl = ShoppingList(guild_id="111", meal_plan_id=mp.id, generated_at=datetime.utcnow())
    session.add(old_sl)
    session.commit()
    old_id = old_sl.id
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_generate.callback(cog, mock_interaction)
    assert session.get(ShoppingList, old_id) is None
    assert session.query(ShoppingList).filter_by(guild_id="111").count() == 1


@pytest.mark.asyncio
async def test_shopping_view_no_list(session, bot, mock_interaction):
    session.add(Guild(guild_id="111", name="Test"))
    session.commit()
    mock_interaction.guild_id = "111"
    mock_interaction.guild.name = "Test"
    cog = ShoppingCog(bot)
    with patch("recipebot.cogs.shopping.current_week_start", return_value=date(2026, 3, 16)):
        await cog.shopping_view.callback(cog, mock_interaction)
    kwargs = mock_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_shopping.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `recipebot/cogs/shopping.py`**

```python
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
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
            upsert_guild(session, guild_id, interaction.guild.name)
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

            # Replace existing shopping list for this meal plan
            existing = session.query(ShoppingList).filter_by(meal_plan_id=meal_plan.id).first()
            if existing:
                session.delete(existing)
                session.commit()

            sl = ShoppingList(
                guild_id=guild_id,
                meal_plan_id=meal_plan.id,
                generated_at=datetime.utcnow(),
            )
            session.add(sl)
            session.commit()
            for item in aggregated:
                session.add(ShoppingListItem(
                    shopping_list_id=sl.id,
                    ingredient_name=item['ingredient_name'],
                    total_quantity=item['total_quantity'],
                    unit=item['unit'],
                    category=item['category'],
                ))
            session.commit()
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
                qty = f"{item.total_quantity:.2f}".rstrip('0').rstrip('.')
                unit = f" {item.unit}" if item.unit else ""
                by_category[cat].append(f"• {item.ingredient_name}: {qty}{unit}")
            for cat in CATEGORY_ORDER:
                if by_category[cat]:
                    embed.add_field(
                        name=cat.capitalize(),
                        value="\n".join(by_category[cat])[:1024],
                        inline=False,
                    )
            await interaction.response.send_message(embed=embed)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add recipebot/cogs/shopping.py tests/test_shopping.py
git commit -m "feat: add shopping generate and view commands"
```

---

### Task 11: End-to-End Smoke Test

**Prerequisites:** Docker and Docker Compose installed. A real Discord bot token in `.env`.

- [ ] **Step 1: Copy `.env.example` to `.env` and fill in values**

```bash
cp .env.example .env
# Edit .env with a real DISCORD_BOT_TOKEN, DB_PASSWORD, DB_ROOT_PASSWORD
```

- [ ] **Step 2: Build and start the stack**

```bash
docker compose up --build
```

Expected output (in order):
1. `percona` starts and becomes healthy (may take 20-30 seconds on first run)
2. `liquibase` runs and logs `Liquibase command 'update' was executed successfully`
3. `liquibase` exits with code 0
4. `recipebot` starts and logs `Logged in as <botname>#<discriminator>`

- [ ] **Step 3: Verify slash commands appear in Discord**

In any Discord server where the bot has been added, type `/recipebot` and confirm all subcommands appear in the autocomplete dropdown.

- [ ] **Step 4: Smoke test each command group**

1. `/recipebot add` — fill modal, confirm recipe created
2. `/recipebot ingredients <recipe>` — add ingredients, confirm no errors
3. `/recipebot instructions <recipe>` — add steps
4. `/recipebot tag <recipe>` — add tags
5. `/recipebot view <recipe>` — confirm embed shows all data
6. `/recipebot search by:name query:partial` — confirm results
7. `/recipebot plan-add recipe:<name> day:monday meal_type:dinner servings:2`
8. `/recipebot plan-view` — confirm meal plan embed
9. `/recipebot shopping-generate` — confirm success message
10. `/recipebot shopping-view` — confirm categorized embed
11. `/recipebot edit <recipe>` — edit fields, confirm update
12. `/recipebot delete <recipe>` — confirm + delete

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat: complete discord recipe bot implementation"
```
