#!/usr/bin/env python3
"""
Merge all tech-* categories with < 100 tweets into 'technical'.
"""

import duckdb

def main():
    conn = duckdb.connect('twitter.db')
    
    # Get all tech-* categories with < 100 tweets
    result = conn.execute('''
        SELECT category, COUNT(*) as cnt 
        FROM tweet_categories 
        WHERE category LIKE 'tech-%' AND category != 'technical'
        GROUP BY category 
        HAVING COUNT(*) < 100
        ORDER BY cnt ASC
    ''').fetchall()
    
    print(f"Found {len(result)} tech-* categories with < 100 tweets")
    
    # Check current 'technical' count
    tech_count = conn.execute('''
        SELECT COUNT(*) FROM tweet_categories WHERE category = 'technical'
    ''').fetchone()[0]
    print(f"Current 'technical' category: {tech_count} tweets")
    
    total_to_merge = sum(cnt for cat, cnt in result)
    print(f"Will merge {total_to_merge} tweets from {len(result)} categories")
    print(f"Final 'technical' will have: {tech_count + total_to_merge} tweets")
    print()
    
    response = input("Proceed with merge? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    # Begin transaction
    conn.execute("BEGIN TRANSACTION")
    
    try:
        merged = 0
        for cat, cnt in result:
            conn.execute(
                "UPDATE tweet_categories SET category = 'technical' WHERE category = ?",
                [cat]
            )
            # Remove from custom_categories
            conn.execute(
                "DELETE FROM custom_categories WHERE category_name = ?",
                [cat]
            )
            merged += cnt
            if merged % 500 == 0:
                print(f"  Merged {merged}/{total_to_merge} tweets...")
        
        # Commit
        conn.execute("COMMIT")
        
        # Verify
        final_count = conn.execute('''
            SELECT COUNT(*) FROM tweet_categories WHERE category = 'technical'
        ''').fetchone()[0]
        
        print(f"\n✅ Done! 'technical' now has {final_count} tweets")
        
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\n❌ Error: {e}")
        print("Transaction rolled back")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()

