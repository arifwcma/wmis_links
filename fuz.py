#!/usr/bin/env python3
"""
fuz.py - Fuzzy string matching utility.
"""


def fuzzy_match(a, b):
    """
    Returns a fuzzy string match score between a and b.
    Score is between 0.0 (no match) and 1.0 (exact match).
    Uses Levenshtein distance-based similarity ratio.
    """
    if a == b:
        return 1.0
    
    if not a or not b:
        return 0.0
    
    # Convert to lowercase for case-insensitive matching
    a = a.lower()
    b = b.lower()
    
    if a == b:
        return 1.0
    
    # Calculate Levenshtein distance
    len_a, len_b = len(a), len(b)
    
    # Create distance matrix
    dp = [[0] * (len_b + 1) for _ in range(len_a + 1)]
    
    # Initialize base cases
    for i in range(len_a + 1):
        dp[i][0] = i
    for j in range(len_b + 1):
        dp[0][j] = j
    
    # Fill the matrix
    for i in range(1, len_a + 1):
        for j in range(1, len_b + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # deletion
                    dp[i][j - 1],      # insertion
                    dp[i - 1][j - 1]   # substitution
                )
    
    distance = dp[len_a][len_b]
    max_len = max(len_a, len_b)
    
    # Convert distance to similarity score (0.0 to 1.0)
    similarity = 1.0 - (distance / max_len)
    
    return round(similarity, 4)


if __name__ == '__main__':
    a = "AVOCA RIVER AT CHARLTON TOWN"
    b = "AVOCA RIVER AT D/S CHARLTON"
    
    x = "AVOCA RIVER @ QUAMBATOOK"
    y = "AVOCA RIVER @ CHARLTON"
    

    print(fuzzy_match(a, x))
    print(fuzzy_match(a, y))
