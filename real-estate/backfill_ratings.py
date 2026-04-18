"""
Backfill rating and nutrition fields for existing recipes by re-fetching
their pages and extracting aggregateRating + nutrition from the JSON-LD.
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from listings.utils import DB_PATH
from nyt_recipe_ingest import build_session, extract_jsonld

HTTP_WORKERS = 10

NUTRITION_FIELDS = [
    "calories", "protein_g", "fat_g", "saturated_fat_g", "unsaturated_fat_g",
    "trans_fat_g", "carbs_g", "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg",
]


def fetch_fields(session, row: sqlite3.Row) -> dict | None:
    """Fetch a recipe page and return all rating + nutrition fields."""
    try:
        resp = session.get(row["recipe_url"], timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        data = extract_jsonld(soup)
        return {"id": row["id"], **{k: data.get(k) for k in
                ["rating_value", "rating_count"] + NUTRITION_FIELDS}}
    except Exception as exc:
        print(f"  Failed {row['recipe_url']}: {exc}")
        return None


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    session = build_session()

    rows = conn.execute(
        "SELECT id, recipe_url FROM recipes WHERE recipe_url IS NOT NULL"
    ).fetchall()
    print(f"Backfilling ratings + nutrition for {len(rows)} recipes…")

    updated = 0
    with ThreadPoolExecutor(max_workers=HTTP_WORKERS) as pool:
        futures = [pool.submit(fetch_fields, session, r) for r in rows]
        for future in as_completed(futures):
            result = future.result()
            if not result:
                continue
            rid = result.pop("id")
            set_clause = ", ".join(f"{k}=?" for k in result)
            conn.execute(
                f"UPDATE recipes SET {set_clause} WHERE id=?",
                list(result.values()) + [rid],
            )
            updated += 1

    conn.commit()
    print(f"Done. {updated}/{len(rows)} recipes updated.")

    sample = conn.execute(
        "SELECT name, calories, protein_g, fat_g, carbs_g, rating_value, rating_count "
        "FROM recipes WHERE calories IS NOT NULL ORDER BY rating_count DESC LIMIT 5"
    ).fetchall()
    print("\nTop 5 by review count (with nutrition):")
    for r in sample:
        print(f"  ⭐{r['rating_value']} ({r['rating_count']}) {r['name']} — "
              f"{r['calories']} cal | {r['protein_g']}g protein | "
              f"{r['fat_g']}g fat | {r['carbs_g']}g carbs")

    conn.close()


if __name__ == "__main__":
    main()
