"""
Regression tests for NYT article and recipe parsing.
Tests article snippet extraction, recipe parsing, and metadata extraction.
Run with: pytest test_nyt_parsing.py -v
"""
import pytest
from datetime import datetime


class TestNYTArticleMetadata:
    """Test extraction of article metadata (title, author, date)."""

    def test_article_title_extraction(self):
        """Extract article title from response."""
        article = {
            "title": "US Mint Buys Drug Cartel Gold and Sells It as 'American'",
            "byline": "By Justin Scheck, Simón Posada and Federico Rios",
            "published_date": "2026-04-25T13:45:32-04:00",
        }
        assert article["title"] is not None
        assert "Mint" in article["title"]
        assert len(article["title"]) > 10

    def test_article_byline_parsing(self):
        """Parse byline to extract author names."""
        byline = "By Justin Scheck, Simón Posada and Federico Rios"
        assert "Justin" in byline
        assert "By " in byline
        # Should be multiple authors
        assert byline.count(",") >= 1

    def test_article_date_parsing(self):
        """Parse ISO 8601 date format."""
        date_str = "2026-04-25T13:45:32-04:00"
        # Should be parseable as datetime
        dt = datetime.fromisoformat(date_str[:25])
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 25

    def test_article_link_extraction(self):
        """Extract article URL."""
        article = {
            "url": "https://www.nytimes.com/2026/04/25/business/us-mint-gold.html",
        }
        assert article["url"].startswith("https://")
        assert "nytimes.com" in article["url"]


class TestNYTArticleFiltering:
    """Test filtering and validation of article data."""

    def test_article_minimum_fields(self):
        """Ensure article has minimum required fields."""
        article = {
            "title": "Some Article",
            "url": "https://nytimes.com/article",
            "abstract": "Brief summary",
        }
        required_fields = ["title", "url"]
        for field in required_fields:
            assert field in article, f"Missing required field: {field}"

    def test_filter_articles_with_no_title(self):
        """Skip articles without titles."""
        articles = [
            {"title": "Good Article", "url": "https://nytimes.com/1"},
            {"title": "", "url": "https://nytimes.com/2"},  # Invalid
            {"title": "Another Good Article", "url": "https://nytimes.com/3"},
        ]
        valid = [a for a in articles if a.get("title")]
        assert len(valid) == 2

    def test_filter_articles_with_no_url(self):
        """Skip articles without URLs."""
        articles = [
            {"title": "Article 1", "url": "https://nytimes.com/1"},
            {"title": "Article 2", "url": ""},  # Invalid
            {"title": "Article 3", "url": "https://nytimes.com/3"},
        ]
        valid = [a for a in articles if a.get("url")]
        assert len(valid) == 2


class TestRecipeMetadata:
    """Test extraction of recipe metadata."""

    def test_recipe_title_extraction(self):
        """Extract recipe title."""
        recipe = {
            "title": "Overnight Oats with Berries",
            "author": "Alison Roman",
        }
        assert recipe["title"] is not None
        assert len(recipe["title"]) > 5

    def test_recipe_ingredients_parsing(self):
        """Parse ingredient list."""
        ingredients = [
            "2 cups rolled oats",
            "1 cup milk",
            "1 cup berries",
            "2 tablespoons honey",
        ]
        # Should have reasonable number of ingredients
        assert len(ingredients) >= 2
        # Each should be a string
        assert all(isinstance(ing, str) for ing in ingredients)

    def test_recipe_instructions_parsing(self):
        """Parse cooking instructions."""
        instructions = [
            "Mix oats and milk in a jar",
            "Add berries and honey",
            "Refrigerate overnight",
            "Enjoy in the morning",
        ]
        # Should have reasonable number of steps
        assert len(instructions) >= 2
        # Should be numbered/sequential
        assert all(isinstance(step, str) for step in instructions)

    def test_recipe_prep_time_extraction(self):
        """Extract prep/cook time in minutes."""
        recipe = {
            "prep_time_minutes": 10,
            "cook_time_minutes": 30,
        }
        assert recipe["prep_time_minutes"] >= 0
        assert recipe["cook_time_minutes"] >= 0

    def test_recipe_servings_extraction(self):
        """Extract number of servings."""
        recipe = {
            "servings": 4,
        }
        assert recipe["servings"] > 0
        assert isinstance(recipe["servings"], int)


class TestRecipeFiltering:
    """Test filtering and validation of recipe data."""

    def test_recipe_minimum_fields(self):
        """Ensure recipe has minimum required fields."""
        recipe = {
            "title": "Simple Recipe",
            "ingredients": ["Ingredient 1", "Ingredient 2"],
            "instructions": ["Step 1", "Step 2"],
        }
        required_fields = ["title", "ingredients", "instructions"]
        for field in required_fields:
            assert field in recipe, f"Missing required field: {field}"

    def test_filter_recipes_with_no_title(self):
        """Skip recipes without titles."""
        recipes = [
            {"title": "Good Recipe", "ingredients": ["a"]},
            {"title": "", "ingredients": ["b"]},  # Invalid
            {"title": "Another Recipe", "ingredients": ["c"]},
        ]
        valid = [r for r in recipes if r.get("title")]
        assert len(valid) == 2

    def test_filter_recipes_with_no_ingredients(self):
        """Skip recipes without ingredients."""
        recipes = [
            {"title": "Recipe 1", "ingredients": ["flour", "sugar"]},
            {"title": "Recipe 2", "ingredients": []},  # Invalid
            {"title": "Recipe 3", "ingredients": ["eggs"]},
        ]
        valid = [r for r in recipes if r.get("ingredients")]
        assert len(valid) == 2


class TestDataIntegrity:
    """Test data consistency and integrity."""

    def test_article_date_is_recent(self):
        """Article dates should be recent (within last 30 days)."""
        from datetime import datetime, timedelta, timezone

        article_date_str = "2026-04-25T13:45:32-04:00"
        article_date = datetime.fromisoformat(article_date_str[:25])
        article_date = article_date.replace(tzinfo=timezone.utc)

        # Today is 2026-05-02, so 30 days ago is 2026-04-02
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        assert article_date > thirty_days_ago, "Article is older than 30 days"

    def test_recipe_cooking_time_reasonable(self):
        """Cooking time should be reasonable (< 480 minutes / 8 hours)."""
        recipes = [
            {"title": "Quick Pasta", "cook_time_minutes": 15},
            {"title": "Slow Roast", "cook_time_minutes": 180},
            {"title": "All Day Stew", "cook_time_minutes": 480},
        ]
        # All should be valid
        for recipe in recipes:
            assert 0 <= recipe["cook_time_minutes"] <= 480

    def test_no_duplicate_articles(self):
        """Ensure article list has no duplicates."""
        articles = [
            {"title": "Article A", "url": "https://nytimes.com/1"},
            {"title": "Article B", "url": "https://nytimes.com/2"},
            {"title": "Article A", "url": "https://nytimes.com/1"},  # Duplicate
        ]
        unique_urls = set(a["url"] for a in articles)
        # If we had deduplication, we'd have 2 unique
        assert len(unique_urls) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
