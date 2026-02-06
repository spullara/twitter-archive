#!/usr/bin/env python3
"""
Merge two tweet categories by updating all tweets from source to target category
and removing the source category from the category list.

Usage:
    python merge_categories.py <source_category> <target_category>
    
Example:
    python merge_categories.py "brief-social-interaction" "brief-interaction"
"""

import duckdb
import sys
from pathlib import Path

def merge_categories(source: str, target: str, db_path: str = "twitter.db"):
    """
    Merge source category into target category.
    
    Args:
        source: Category to merge from (will be removed)
        target: Category to merge into (will be kept)
        db_path: Path to the DuckDB database
    """
    conn = duckdb.connect(db_path)
    
    try:
        # Check if both categories exist
        source_count = conn.execute(
            "SELECT COUNT(*) FROM tweet_categories WHERE category = ?", [source]
        ).fetchone()[0]

        target_count = conn.execute(
            "SELECT COUNT(*) FROM tweet_categories WHERE category = ?", [target]
        ).fetchone()[0]
        
        if source_count == 0:
            print(f"❌ Source category '{source}' not found or has no tweets")
            return False
            
        if target_count == 0:
            print(f"⚠️  Warning: Target category '{target}' not found or has no tweets")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                return False
        
        print(f"\n📊 Merge Summary:")
        print(f"  Source: {source} ({source_count:,} tweets)")
        print(f"  Target: {target} ({target_count:,} tweets)")
        print(f"  Result: {target} ({source_count + target_count:,} tweets)")
        
        # Confirm the merge
        response = input(f"\n⚠️  Merge '{source}' into '{target}'? (y/n): ")
        if response.lower() != 'y':
            print("❌ Merge cancelled")
            return False

        # Begin transaction
        conn.execute("BEGIN TRANSACTION")

        try:
            # Update all tweet categories from source to target category
            conn.execute(
                "UPDATE tweet_categories SET category = ? WHERE category = ?",
                [target, source]
            )

            # Remove source category from custom_categories if it exists
            conn.execute(
                "DELETE FROM custom_categories WHERE category_name = ?",
                [source]
            )

            # Verify the merge before committing
            remaining = conn.execute(
                "SELECT COUNT(*) FROM tweet_categories WHERE category = ?", [source]
            ).fetchone()[0]

            new_target_count = conn.execute(
                "SELECT COUNT(*) FROM tweet_categories WHERE category = ?", [target]
            ).fetchone()[0]

            if remaining == 0 and new_target_count == source_count + target_count:
                # Commit the transaction
                conn.execute("COMMIT")
                print(f"\n✅ Successfully merged {source_count:,} tweets from '{source}' into '{target}'")
                print(f"   New total for '{target}': {new_target_count:,} tweets")
                return True
            else:
                # Rollback if verification failed
                conn.execute("ROLLBACK")
                print(f"\n❌ Merge verification failed! Transaction rolled back.")
                print(f"   Remaining in source: {remaining}")
                print(f"   Expected in target: {source_count + target_count}")
                print(f"   Actual in target: {new_target_count}")
                return False

        except Exception as e:
            # Rollback on any error
            conn.execute("ROLLBACK")
            print(f"\n❌ Error during merge: {e}")
            print("   Transaction rolled back - no changes made")
            raise
            
    except Exception as e:
        print(f"❌ Error during merge: {e}")
        return False
    finally:
        conn.close()

def main():
    if len(sys.argv) != 3:
        print("Usage: python merge_categories.py <source_category> <target_category>")
        print("\nExample:")
        print('  python merge_categories.py "brief-social-interaction" "brief-interaction"')
        sys.exit(1)
    
    source = sys.argv[1]
    target = sys.argv[2]
    
    if source == target:
        print("❌ Source and target categories cannot be the same")
        sys.exit(1)
    
    success = merge_categories(source, target)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

