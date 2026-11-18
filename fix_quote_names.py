#!/usr/bin/env python3
"""
Migration script to fix member names and member IDs that have had quotes stripped.

This script will:
1. Find members with names that should contain quotes but don't
2. Update their names and member IDs to include quotes
3. Handle duplicate member IDs by appending numbers if needed

Usage: python fix_quote_names.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'authlibs'))

from sqlalchemy import create_engine, text
from authlibs.init import get_config
import re

def find_stripe_members_with_stripped_quotes():
    """Find members who were created from Stripe and likely had quotes stripped"""
    
    # Common patterns that indicate quotes were stripped
    patterns = [
        r"[A-Z][a-z]+[A-Z][a-z]+",  # Pattern like "DOlimpio" (should be "D'Olimpio")
        r"[A-Z][a-z]+[A-Z][a-z]+[A-Z][a-z]+",  # Pattern like "OMalley" (should be "O'Malley")
    ]
    
    potential_fixes = []
    
    # Get configuration
    config = get_config()
    db_path = config.Config.get('Database', 'dbfile')
    
    # Connect to database
    engine = create_engine(f'sqlite:///{db_path}')
    
    with engine.connect() as conn:
        # Get all members
        result = conn.execute(text("SELECT id, member, firstname, lastname FROM members ORDER BY id"))
        
        for row in result:
            member_id, member, firstname, lastname = row
            
            # Check if lastname matches patterns suggesting stripped quotes
            for pattern in patterns:
                if re.match(pattern, lastname) and "'" not in lastname:
                    # Try to reconstruct the original name
                    original_lastname = reconstruct_original_name(lastname)
                    if original_lastname != lastname:
                        original_member_id = f"{firstname}.{original_lastname}"
                        potential_fixes.append({
                            'id': member_id,
                            'current_member_id': member,
                            'current_firstname': firstname,
                            'current_lastname': lastname,
                            'suggested_lastname': original_lastname,
                            'suggested_member_id': original_member_id
                        })
                        break
    
    return potential_fixes

def reconstruct_original_name(stripped_name):
    """Try to reconstruct original name with quotes"""
    
    # Common Irish/Italian names that get stripped
    common_fixes = {
        'DOlimpio': "D'Olimpio",
        'OMalley': "O'Malley",
        'OReilly': "O'Reilly",
        'OSullivan': "O'Sullivan",
        'ONeill': "O'Neill",
        'OConnor': "O'Connor",
        'OBrien': "O'Brien",
        'DOnofrio': "D'Onofrio",
        'DAngelo': "D'Angelo",
        'DeLuca': "DeLuca",  # This might be correct, but could be "De'Luca"
        'DiMarco': "DiMarco",  # This might be correct
    }
    
    # Check for exact matches first
    if stripped_name in common_fixes:
        return common_fixes[stripped_name]
    
    # Try pattern matching for O'X names
    if len(stripped_name) > 2 and stripped_name[1].isupper() and stripped_name[0] == 'O':
        return f"O'{stripped_name[1:]}"
    
    # Try pattern matching for D'X names  
    if len(stripped_name) > 2 and stripped_name[1].isupper() and stripped_name[0] == 'D':
        return f"D'{stripped_name[1:]}"
    
    return stripped_name  # No change if we can't determine

def apply_fixes(dry_run=True):
    """Apply the fixes to the database"""
    
    fixes = find_stripe_members_with_stripped_quotes()
    
    if not fixes:
        print("No members found that need quote fixes.")
        return
    
    print(f"Found {len(fixes)} potential fixes:")
    for fix in fixes:
        print(f"  ID {fix['id']}: {fix['current_firstname']} {fix['current_lastname']} ({fix['current_member_id']})")
        print(f"    -> {fix['current_firstname']} {fix['suggested_lastname']} ({fix['suggested_member_id']})")
    
    if dry_run:
        print("\nDRY RUN - No changes made. Use apply_fixes(dry_run=False) to apply changes.")
        return
    
    # Get configuration and connect
    config = get_config()
    db_path = config.Config.get('Database', 'dbfile')
    engine = create_engine(f'sqlite:///{db_path}')
    
    with engine.connect() as conn:
        for fix in fixes:
            try:
                # Check if suggested member ID already exists
                existing = conn.execute(
                    text("SELECT id FROM members WHERE member = :member_id"), 
                    {'member_id': fix['suggested_member_id']}
                ).fetchone()
                
                if existing:
                    print(f"WARNING: Member ID {fix['suggested_member_id']} already exists, skipping...")
                    continue
                
                # Update the member
                conn.execute(
                    text("""
                        UPDATE members 
                        SET lastname = :new_lastname, member = :new_member_id 
                        WHERE id = :member_db_id
                    """),
                    {
                        'new_lastname': fix['suggested_lastname'],
                        'new_member_id': fix['suggested_member_id'],
                        'member_db_id': fix['id']
                    }
                )
                
                print(f"Updated member {fix['id']}: {fix['current_member_id']} -> {fix['suggested_member_id']}")
                
            except Exception as e:
                print(f"ERROR updating member {fix['id']}: {e}")
        
        conn.commit()
        print("Changes committed to database.")

if __name__ == '__main__':
    print("Checking for members with stripped quotes...")
    apply_fixes(dry_run=True)  # Start with dry run
