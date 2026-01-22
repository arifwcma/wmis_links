#!/usr/bin/env python3
"""
replace.py - Creates a copy of source.geojson to "River Gauges.geojson"
by replacing only the "source" fields based on links.csv mappings.
"""

import csv
import json
from datetime import datetime


def load_links_csv(csv_path):
    """Load links.csv and return a dictionary mapping id -> link, plus a set of duplicate ids."""
    id_to_link = {}
    duplicate_ids = set()
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Trim the id and use it as key
            row_id = row['id'].strip()
            row_link = row['link'].strip() if row['link'] else ''
            
            # Check if this id already exists (duplicate)
            if row_id in id_to_link:
                duplicate_ids.add(row_id)
            
            # Store the first occurrence's link
            if row_id not in id_to_link:
                id_to_link[row_id] = row_link
    
    return id_to_link, duplicate_ids


def process_geojson(source_path, output_path, id_to_link, duplicate_ids, log_path):
    """
    Read source.geojson, replace 'source' fields based on id_to_link mapping,
    write to output_path, and generate a log file.
    """
    # Load the source GeoJSON
    with open(source_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    found_list = []
    not_found_list = []
    multiple_match_list = []
    
    # Process each feature
    for feature in geojson_data.get('features', []):
        properties = feature.get('properties', {})
        
        if properties is None:
            continue
        
        prop_id = properties.get('id')
        prop_name = properties.get('name')
        
        if prop_id is None:
            continue
        
        # Trim the id for matching
        prop_id_trimmed = str(prop_id).strip()
        
        # Search for matching row in links.csv
        if prop_id_trimmed in id_to_link:
            # Found - update the source field
            properties['source'] = id_to_link[prop_id_trimmed]
            found_list.append((prop_name, prop_id_trimmed))
            
            # Check if this id had multiple matches in the CSV
            if prop_id_trimmed in duplicate_ids:
                multiple_match_list.append((prop_name, prop_id_trimmed))
        else:
            # Not found
            not_found_list.append((prop_name, prop_id_trimmed))
    
    # Write the updated GeoJSON to output file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, indent=2)
    
    # Generate the log file
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"replace.py Log - Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        # (1) Found and updated properties
        f.write("(1) FOUND AND UPDATED PROPERTIES\n")
        f.write("-" * 40 + "\n")
        for name, pid in found_list:
            f.write(f"  Name: {name}, ID: {pid}\n")
        f.write(f"\nTotal found and updated: {len(found_list)}\n\n")
        
        # (2) Not found properties
        f.write("(2) NOT FOUND PROPERTIES\n")
        f.write("-" * 40 + "\n")
        for name, pid in not_found_list:
            f.write(f"  Name: {name}, ID: {pid}\n")
        f.write(f"\nTotal not found: {len(not_found_list)}\n\n")
        
        # (3) Properties with multiple ID matches in links.csv
        f.write("(3) PROPERTIES WITH MULTIPLE ID MATCHES IN links.csv\n")
        f.write("-" * 40 + "\n")
        for name, pid in multiple_match_list:
            f.write(f"  Name: {name}, ID: {pid}\n")
        f.write(f"\nTotal with multiple matches: {len(multiple_match_list)}\n")
    
    return len(found_list), len(not_found_list), len(multiple_match_list)


def main():
    csv_path = 'links.csv'
    source_path = 'source.geojson'
    output_path = 'River Gauges.geojson'
    log_path = 'replace.log'
    
    print(f"Loading links from {csv_path}...")
    id_to_link, duplicate_ids = load_links_csv(csv_path)
    print(f"Loaded {len(id_to_link)} link mappings ({len(duplicate_ids)} duplicate IDs found).")
    
    print(f"Processing {source_path}...")
    found_count, not_found_count, multiple_match_count = process_geojson(
        source_path, output_path, id_to_link, duplicate_ids, log_path
    )
    
    print(f"\nDone!")
    print(f"  - Output written to: {output_path}")
    print(f"  - Log written to: {log_path}")
    print(f"  - Found and updated: {found_count}")
    print(f"  - Not found: {not_found_count}")
    print(f"  - Multiple ID matches in CSV: {multiple_match_count}")


if __name__ == '__main__':
    main()
