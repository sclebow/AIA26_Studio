"""Quick test script for embedding_matcher - loads from actual file"""

import json
from pathlib import Path
from tools.embedding_matcher import match_layouts, get_embedding_model

print("1. Testing model load...")
model = get_embedding_model()
print("✓ Model loaded successfully!\n")

print("2. Loading descriptions from sample_descriptions.json...")
descriptions_path = Path(__file__).parent.parent / "layout_inputs" / "sample_descriptions.json"
if descriptions_path.exists():
    with open(descriptions_path) as f:
        all_descriptions = json.load(f)
    print(f"✓ Loaded {len(all_descriptions)} layouts\n")
else:
    print(f"✗ File not found: {descriptions_path}\n")
    exit(1)

print("3. Testing match_layouts with different queries:\n")

test_queries = [
    "We want to share an apartment with 2 bedrooms and private bathrooms",
    "I am looking for a small studio for minimalist living",
    "We are a young couple and want a cozy place with a separate bedroom",
]

for query in test_queries:
    print(f"Query: '{query}'")
    result = match_layouts(
        query=query,
        all_descriptions=all_descriptions,
        top_k=2,
        min_score=0.2
    )
    
    if result["count"] == 0:
        print("  ✗ No matches found\n")
    else:
        for i, match in enumerate(result["matches"], 1):
            print(f"  {i}. {match['layoutId']}: {match['score']:.1%} match")
            print(f"     Area: {match['area']} sqm, Rooms: {', '.join(match['roomTypes'])}")
        print()

print("✓ Test complete!")
