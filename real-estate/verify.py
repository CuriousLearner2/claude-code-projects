#!/usr/bin/env python3
"""Verification script for House Listings Intelligence System."""

import os
import sys

def check_imports():
    """Check all modules import successfully."""
    print("📦 Checking imports...")
    try:
        from listings import db, utils, gmail_ingest, scraper, geocoder, reddit_enrichment, query_interface
        print("  ✓ All core modules")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def check_database():
    """Check database initialization."""
    print("\n📊 Checking database...")
    try:
        from listings.db import init_db
        from listings.utils import DB_PATH
        import os

        # Use temp DB for test
        test_db = "/tmp/listings_test.db"
        if os.path.exists(test_db):
            os.remove(test_db)

        conn = init_db(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = {"sync_state", "listings", "geocode_cache", "neighborhood_sentiment", "reddit_posts"}
        actual_tables = set(tables) - {"sqlite_sequence"}

        if expected_tables.issubset(actual_tables):
            print(f"  ✓ Database schema ({len(actual_tables)} tables)")
            conn.close()
            os.remove(test_db)
            return True
        else:
            print(f"  ✗ Missing tables: {expected_tables - actual_tables}")
            return False
    except Exception as e:
        print(f"  ✗ Database check failed: {e}")
        return False


def check_gmail_auth():
    """Check Gmail authentication."""
    print("\n🔐 Checking Gmail credentials...")
    try:
        from listings.utils import TOKEN_FILE, CREDS_FILE
        import os

        if os.path.exists(CREDS_FILE):
            print(f"  ✓ credentials.json found")
            if os.path.exists(TOKEN_FILE):
                print(f"  ✓ token.json found (authenticated)")
            else:
                print(f"  ℹ token.json not found (will authenticate on first sync)")
            return True
        else:
            print(f"  ✗ credentials.json not found")
            return False
    except Exception as e:
        print(f"  ✗ Gmail check failed: {e}")
        return False


def check_anthropic():
    """Check Anthropic API key."""
    print("\n🤖 Checking Anthropic API...")
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            print(f"  ✓ ANTHROPIC_API_KEY set")
            # Try to instantiate client (won't make API call)
            from listings.utils import get_anthropic_client
            client = get_anthropic_client()
            print(f"  ✓ Client initialized")
            return True
        else:
            print(f"  ✗ ANTHROPIC_API_KEY not set")
            return False
    except Exception as e:
        print(f"  ✗ Anthropic check failed: {e}")
        return False


def check_reddit():
    """Check Reddit credentials (optional)."""
    print("\n🔗 Checking Reddit credentials (optional)...")
    try:
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        username = os.environ.get("REDDIT_USERNAME")

        if all([client_id, client_secret, username]):
            print(f"  ✓ Reddit credentials found")
            return True
        else:
            missing = []
            if not client_id:
                missing.append("REDDIT_CLIENT_ID")
            if not client_secret:
                missing.append("REDDIT_CLIENT_SECRET")
            if not username:
                missing.append("REDDIT_USERNAME")
            print(f"  ℹ Not configured: {', '.join(missing)}")
            print(f"  ℹ Run: python3 setup_reddit.py")
            return True  # Optional, so don't fail
    except Exception as e:
        print(f"  ✗ Reddit check failed: {e}")
        return False


def check_playwright():
    """Check Playwright is installed."""
    print("\n🎭 Checking Playwright...")
    try:
        from playwright.async_api import async_playwright
        print(f"  ✓ Playwright installed")
        return True
    except ImportError:
        print(f"  ✗ Playwright not installed")
        print(f"  ℹ Run: pip install playwright && playwright install chromium")
        return False


def check_scripts():
    """Check entry point scripts."""
    print("\n📝 Checking entry point scripts...")
    import os
    import stat

    scripts = ["sync.py", "query.py", "setup_reddit.py"]
    all_ok = True

    for script in scripts:
        path = os.path.join("/Users/gautambiswas/Claude Code", script)
        if os.path.exists(path):
            st = os.stat(path)
            is_executable = bool(st.st_mode & stat.S_IXUSR)
            if is_executable:
                print(f"  ✓ {script}")
            else:
                print(f"  ⚠ {script} (not executable)")
                all_ok = False
        else:
            print(f"  ✗ {script} not found")
            all_ok = False

    return all_ok


def main():
    print("🏠 House Listings Intelligence System - Verification\n")
    print("=" * 50)

    checks = [
        ("Imports", check_imports),
        ("Database", check_database),
        ("Gmail Auth", check_gmail_auth),
        ("Anthropic API", check_anthropic),
        ("Reddit (Optional)", check_reddit),
        ("Playwright", check_playwright),
        ("Entry Scripts", check_scripts),
    ]

    results = []
    for name, check in checks:
        try:
            result = check()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("\n📋 Summary:")

    all_ok = True
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
        if name not in ["Reddit (Optional)"] and not result:
            all_ok = False

    print("\n" + "=" * 50)

    if all_ok:
        print("\n✓ System is ready!")
        print("\nNext steps:")
        print("  1. Run: python3 sync.py --skip-reddit")
        print("  2. Wait for ingestion, geocoding, and scraping to complete")
        print("  3. Query: python3 query.py 'Show all listings'")
        return 0
    else:
        print("\n✗ Some checks failed. See above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
