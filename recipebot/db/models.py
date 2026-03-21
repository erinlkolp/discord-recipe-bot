from datetime import datetime, timezone
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
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
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
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
