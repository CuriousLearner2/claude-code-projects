#!/usr/bin/env python3
"""Natural language search interface for house listings."""

import argparse
import sys

from listings.db import init_db
from listings.query_interface import run_query_interface
from listings.utils import DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Search house listings with natural language")
    parser.add_argument("query", nargs="?", help="Query (optional — omit for interactive mode)")
    args = parser.parse_args()

    # Initialize database (won't create if exists)
    conn = init_db(DB_PATH)

    if args.query:
        # Single-shot mode
        run_query_interface(conn, args.query)
    else:
        # Interactive REPL mode
        run_query_interface(conn)

    conn.close()


if __name__ == "__main__":
    main()
