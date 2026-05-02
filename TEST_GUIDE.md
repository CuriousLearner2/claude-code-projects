# Regression Test Guide

This project includes comprehensive regression tests for all database ingestion scripts. **Run these tests every time you make changes** to listing, article, or recipe parsing code.

## Quick Start

Run all tests:
```bash
python3 run_all_tests.py
```

Expected output:
```
✅ All tests passed!
✓ 18 passed, 0 failed
```

## Test Coverage

### Real-Estate Listing Ingest (`real-estate/test_listing_ingest.py`)
Tests address, price, and square footage extraction from emails:

- ✓ Address extraction from subject lines
- ✓ Price extraction ($1.4M, $850K, etc.)
- ✓ Square footage extraction (1,200 sqft, 1500 sq ft, etc.)
- ✓ **Regression: sqft not included in address** (critical fix)
- ✓ Sanity checks for unreasonable values

### NYT Article Parsing (`nyt/test_nyt_parsing.py`)
Tests article metadata and filtering:

- ✓ Article title extraction
- ✓ Article URL/link extraction
- ✓ Author byline parsing
- ✓ Publication date parsing (ISO 8601)
- ✓ Filtering articles with missing fields
- ✓ Deduplication logic

### NYT Recipe Parsing (`nyt/test_nyt_parsing.py`)
Tests recipe metadata and structure:

- ✓ Recipe title extraction
- ✓ Ingredient list parsing
- ✓ Cooking instructions parsing
- ✓ Prep/cook time extraction
- ✓ Servings count extraction
- ✓ Filtering recipes with missing fields
- ✓ Reasonable cooking time validation

## When to Run Tests

**Before committing code:**
```bash
# Make your changes to ingest scripts
python3 run_all_tests.py

# If all pass, commit and push
git add <modified files>
git commit -m "fix: ..."
git push origin main
```

**After fixing a bug:**
```bash
# The relevant regression test should pass
# Example: fixed sqft-in-address bug
python3 run_all_tests.py
# → sqft_regression: PASS
```

**Before deploying to production:**
```bash
# Run full test suite to catch regressions
python3 run_all_tests.py
```

## Test Failures

If a test fails, it indicates a regression or bug:

```
❌ address_simple: FAIL (got '123 Oak St list', expected '123 Oak St')
```

**What to do:**
1. Identify which script failed (address extraction in this case)
2. Review your recent changes to that script
3. Fix the bug
4. Run tests again to verify the fix
5. Add a new test case to prevent regression

Example:
```python
def test_address_extraction_new_format(self):
    """New test case for the bug you just found."""
    subject = "123 Oak St list available"
    addr = extract_address_from_subject(subject)
    assert "123 Oak St" in addr  # Should pass now
```

## Architecture

```
run_all_tests.py          ← Master test runner (run this)
├── real-estate/
│   ├── test_listing_ingest.py    ← Listing parsing tests
│   └── listings/gmail_ingest.py  ← Functions being tested
└── nyt/
    ├── test_nyt_parsing.py       ← Article/recipe tests
    ├── nyt_digest.py             ← Functions being tested
    └── nyt_recipe_ingest.py      ← Functions being tested
```

## Extending Tests

To add a new test for a bug you find:

1. **Identify the bug:** e.g., "Cleveland listings not parsing correctly"
2. **Add a test case:**
   ```python
   def test_cleveland_address_extraction(self):
       """Regression test for Cleveland address parsing."""
       address = "2500 Euclid Ave, Cleveland OH"
       result = extract_address_from_subject(f"at {address}")
       assert "2500 Euclid Ave" in result
   ```
3. **Verify it fails:** `python3 run_all_tests.py` → ❌
4. **Fix the code:** Update the extraction function
5. **Verify it passes:** `python3 run_all_tests.py` → ✅
6. **Commit both:** Test + fix together

## Continuous Integration (Future)

These tests are ready for CI/CD integration. Example GitHub Actions workflow:

```yaml
name: Regression Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - run: python3 run_all_tests.py
```

## Troubleshooting

**"ModuleNotFoundError: No module named 'listings'"**
- Make sure you're running from the Claude Code root directory
- The test runner adds both real-estate and nyt to sys.path

**"No module named 'nyt_digest'"**
- Same issue - run from root directory: `python3 run_all_tests.py`

**Tests pass locally but fail in CI**
- Check Python version (should be 3.11+)
- Ensure all dependencies are installed
- Verify email HTML samples in tests are realistic

---

**Last updated:** 2026-05-02
**Total test coverage:** 18 regression tests across 3 components
