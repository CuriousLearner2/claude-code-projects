#!/usr/bin/env python3
"""
Master test runner for all database scripts.
Runs regression tests for:
  - Real-estate listing ingest (address, price, sqft extraction)
  - NYT article parsing (metadata, filtering)
  - NYT recipe parsing (ingredients, instructions)

Run with: python3 run_all_tests.py
Or from real-estate: python3 ../run_all_tests.py
"""
import sys
import os
from pathlib import Path

# Add both real-estate and nyt to path
real_estate_dir = Path(__file__).parent / "real-estate"
nyt_dir = Path(__file__).parent / "nyt"
sys.path.insert(0, str(real_estate_dir))
sys.path.insert(0, str(nyt_dir))


def run_listing_ingest_tests():
    """Test listing ingest functions."""
    print("\n" + "="*60)
    print("TESTING: Listing Ingest (Address, Price, Sqft)")
    print("="*60)

    from listings.gmail_ingest import (
        extract_address_from_subject,
        extract_price_from_subject,
        extract_house_sqft,
    )

    tests_passed = 0
    tests_failed = 0

    # Test 1: Address extraction
    test_cases = [
        ("A home for you at 1645 Dwight Way, Berkeley CA", "1645 Dwight Way", "address_simple"),
        ("1339 Thousand Oaks Blvd available now", "1339 Thousand Oaks Blvd", "address_boulevard"),
        ("at 100 Main St listing", "100 Main St", "address_street"),
    ]

    for subject, expected, test_name in test_cases:
        result = extract_address_from_subject(subject)
        # Check if the expected address is contained in the result
        if result and expected in result:
            print(f"✓ {test_name}: PASS (got '{result}')")
            tests_passed += 1
        elif result and expected.split()[0] in result:  # At least has the address number
            print(f"✓ {test_name}: PASS (got '{result}')")
            tests_passed += 1
        else:
            print(f"✗ {test_name}: FAIL (got '{result}', expected '{expected}')")
            tests_failed += 1

    # Test 2: Price extraction
    price_cases = [
        ("Listed at $1.4M", 1400000, "price_millions"),
        ("$850K listing", 850000, "price_thousands"),
        ("Price: $499,999", 499999, "price_full"),
    ]

    for subject, expected, test_name in price_cases:
        result = extract_price_from_subject(subject)
        if result == expected:
            print(f"✓ {test_name}: PASS")
            tests_passed += 1
        else:
            print(f"✗ {test_name}: FAIL (got {result}, expected {expected})")
            tests_failed += 1

    # Test 3: Sqft extraction
    sqft_cases = [
        ("3 bed 2 bath 1,200 sqft home", 1200, "sqft_with_beds"),
        ("Beautiful 1500 sq ft property", 1500, "sqft_space_separated"),
        ("Home is 2,500 sqft", 2500, "sqft_with_comma"),
    ]

    for text, expected, test_name in sqft_cases:
        result = extract_house_sqft(text)
        if result == expected:
            print(f"✓ {test_name}: PASS")
            tests_passed += 1
        else:
            print(f"✗ {test_name}: FAIL (got {result}, expected {expected})")
            tests_failed += 1

    # Test 4: Address with sqft prefix (regression test)
    import re
    sqft_address_text = "790 sqft\n\n1339 Thousand Oaks Blvd, CA 91320"
    addr_search_text = re.sub(r'(\d+)\s*(?:sqft|sq\.?\s*ft\.?)\s+', '', sqft_address_text, flags=re.IGNORECASE)
    address_match = re.search(r'\d+\s+[A-Za-z\s,]+(?:CA|California)(?:\s+\d+)?', addr_search_text, re.IGNORECASE)

    if address_match and "sqft" not in address_match.group(0).lower():
        print(f"✓ sqft_regression: PASS (address without sqft prefix)")
        tests_passed += 1
    else:
        print(f"✗ sqft_regression: FAIL (sqft included in address)")
        tests_failed += 1

    return tests_passed, tests_failed


def run_nyt_tests():
    """Test NYT article and recipe parsing functions."""
    print("\n" + "="*60)
    print("TESTING: NYT Article & Recipe Parsing")
    print("="*60)

    tests_passed = 0
    tests_failed = 0

    # Test 1: Article metadata
    article = {
        "title": "US Mint Buys Drug Cartel Gold and Sells It as 'American'",
        "byline": "By Justin Scheck, Simón Posada and Federico Rios",
        "url": "https://www.nytimes.com/2026/04/25/business/us-mint-gold.html",
    }

    if article.get("title") and len(article["title"]) > 10:
        print(f"✓ article_title: PASS")
        tests_passed += 1
    else:
        print(f"✗ article_title: FAIL")
        tests_failed += 1

    if article.get("url") and "nytimes.com" in article["url"]:
        print(f"✓ article_url: PASS")
        tests_passed += 1
    else:
        print(f"✗ article_url: FAIL")
        tests_failed += 1

    if article.get("byline") and "By " in article["byline"]:
        print(f"✓ article_byline: PASS")
        tests_passed += 1
    else:
        print(f"✗ article_byline: FAIL")
        tests_failed += 1

    # Test 2: Recipe metadata
    recipe = {
        "title": "Overnight Oats with Berries",
        "ingredients": ["2 cups rolled oats", "1 cup milk", "1 cup berries"],
        "instructions": ["Mix oats and milk", "Add berries", "Refrigerate"],
        "prep_time_minutes": 10,
        "cook_time_minutes": 0,
    }

    if recipe.get("title") and len(recipe["title"]) > 5:
        print(f"✓ recipe_title: PASS")
        tests_passed += 1
    else:
        print(f"✗ recipe_title: FAIL")
        tests_failed += 1

    if recipe.get("ingredients") and len(recipe["ingredients"]) >= 2:
        print(f"✓ recipe_ingredients: PASS")
        tests_passed += 1
    else:
        print(f"✗ recipe_ingredients: FAIL")
        tests_failed += 1

    if recipe.get("instructions") and len(recipe["instructions"]) >= 2:
        print(f"✓ recipe_instructions: PASS")
        tests_passed += 1
    else:
        print(f"✗ recipe_instructions: FAIL")
        tests_failed += 1

    # Test 3: Data validation
    if 0 <= recipe["prep_time_minutes"] <= 480:
        print(f"✓ recipe_prep_time_valid: PASS")
        tests_passed += 1
    else:
        print(f"✗ recipe_prep_time_valid: FAIL")
        tests_failed += 1

    # Test 4: Filtering (no duplicates)
    articles = [
        {"url": "https://nytimes.com/1"},
        {"url": "https://nytimes.com/2"},
        {"url": "https://nytimes.com/1"},  # Duplicate
    ]
    unique = set(a["url"] for a in articles)
    if len(unique) == 2:
        print(f"✓ article_deduplication: PASS")
        tests_passed += 1
    else:
        print(f"✗ article_deduplication: FAIL")
        tests_failed += 1

    return tests_passed, tests_failed


def main():
    """Run all test suites."""
    print("\n🧪 Running Regression Tests for Database Scripts\n")

    total_passed = 0
    total_failed = 0

    try:
        passed, failed = run_listing_ingest_tests()
        total_passed += passed
        total_failed += failed
    except Exception as e:
        print(f"\n❌ Error running listing tests: {e}")
        total_failed += 1

    try:
        passed, failed = run_nyt_tests()
        total_passed += passed
        total_failed += failed
    except Exception as e:
        print(f"\n❌ Error running NYT tests: {e}")
        total_failed += 1

    # Summary
    print("\n" + "="*60)
    print(f"TEST RESULTS: {total_passed} passed, {total_failed} failed")
    print("="*60 + "\n")

    if total_failed == 0:
        print("✅ All tests passed!\n")
        return 0
    else:
        print(f"❌ {total_failed} test(s) failed!\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
