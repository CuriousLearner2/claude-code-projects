#!/usr/bin/env python3
"""Setup Reddit API credentials for sentiment analysis."""

import os
import sys
from pathlib import Path

import praw


def main():
    print("🔐 Reddit API Credential Setup Wizard\n")

    print("To use Reddit sentiment analysis, you need to create an OAuth app:")
    print("1. Visit: https://www.reddit.com/prefs/apps")
    print("2. Click 'Create an app'")
    print("3. Fill in:")
    print("   - name: 'House Listings System'")
    print("   - app type: 'script'")
    print("   - description: 'Neighborhood sentiment analysis'")
    print("   - redirect uri: http://localhost:8080")
    print("4. Click 'Create app'")
    print("5. Note your client ID (below the app name) and client secret\n")

    # Collect credentials
    client_id = input("Enter your Reddit client ID: ").strip()
    if not client_id:
        print("Client ID is required.")
        sys.exit(1)

    client_secret = input("Enter your Reddit client secret: ").strip()
    if not client_secret:
        print("Client secret is required.")
        sys.exit(1)

    username = input("Enter your Reddit username: ").strip()
    if not username:
        print("Username is required.")
        sys.exit(1)

    # Note: For script-based apps, Reddit doesn't require a password if using OAuth
    print("\nNote: If using OAuth token, you may not need a password.")
    password = input("Enter your Reddit password (or press Enter to skip): ").strip()

    # Test connection
    print("\nTesting credentials...")
    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=f"house_listings_system (by {username})",
            username=username,
            password=password if password else None,
        )

        user = reddit.user.me()
        print(f"✓ Connected as: {user.name}\n")

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nPlease check your credentials and try again.")
        sys.exit(1)

    # Print export commands
    print("Add these to your shell profile (~/.zshrc or ~/.bashrc):\n")
    print(f'export REDDIT_CLIENT_ID="{client_id}"')
    print(f'export REDDIT_CLIENT_SECRET="{client_secret}"')
    print(f'export REDDIT_USERNAME="{username}"')
    if password:
        print(f'export REDDIT_PASSWORD="{password}"')

    # Offer to append to ~/.zshrc
    print("\nWould you like to append these to ~/.zshrc? (y/n): ", end="")
    if input().strip().lower() == "y":
        zshrc_path = Path.home() / ".zshrc"
        with open(zshrc_path, "a") as f:
            f.write("\n# Reddit API credentials for House Listings System\n")
            f.write(f'export REDDIT_CLIENT_ID="{client_id}"\n')
            f.write(f'export REDDIT_CLIENT_SECRET="{client_secret}"\n')
            f.write(f'export REDDIT_USERNAME="{username}"\n')
            if password:
                f.write(f'export REDDIT_PASSWORD="{password}"\n')
        print(f"✓ Credentials saved to {zshrc_path}")
        print("Run: source ~/.zshrc")
    else:
        print("\nYou can manually add the export commands above when ready.")

    print("\n✓ Setup complete!")


if __name__ == "__main__":
    main()
