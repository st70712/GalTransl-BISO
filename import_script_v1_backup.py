#!/usr/bin/env python3
"""
BSXScript 3.1 Text Importer for Bishop Engine Games
Imports translated text from JSON back into bsxx.dat

This tool handles the complex task of rebuilding the script file
with translated text while maintaining proper offsets and references.

Author: GalTransl-BGI Project
"""

import struct
import json
import argparse
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class StringEntry:
    """Represents a string entry with its offset and content"""
    index: int
    offset: int
    original: str
    translated: str
    context: str


def load_translation(json_file: Path) -> Tuple[Dict, List[StringEntry]]:
    """
    Load translation data from JSON file.
    
    Returns:
        (script_info, string_entries)
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    script_info = data.get('info', {})
    strings_data = data.get('strings', [])
    
    entries = []
    for s in strings_data:
        entries.append(StringEntry(
            index=s['index'],
            offset=s['offset'],
            original=s['original'],
            translated=s.get('translated', ''),
            context=s.get('context', '')
        ))
    
    # Sort by offset
    entries.sort(key=lambda x: x.offset)
    
    return script_info, entries


def find_string_references(data: bytes, string_table_offset: int, 
                           old_offsets: List[int]) -> Dict[int, List[int]]:
    """
    Find all references to string offsets in the bytecode.
    
    The script likely uses relative or absolute offsets to reference strings.
    We need to find and update these references when string positions change.
    
    Args:
        data: Original script data
        string_table_offset: Offset where string table begins
        old_offsets: List of original string offsets
        
    Returns:
        Dict mapping string offset to list of reference locations in bytecode
    """
    references = {offset: [] for offset in old_offsets}
    
    # Search for 4-byte little-endian values that match string offsets
    # This is a heuristic approach - the actual reference mechanism may vary
    for offset in old_offsets:
        # Convert offset to bytes (little-endian)
        offset_bytes = struct.pack('<I', offset)
        
        # Search in the code section (before string table)
        pos = 0
        while pos < string_table_offset:
            idx = data.find(offset_bytes, pos, string_table_offset)
            if idx == -1:
                break
            references[offset].append(idx)
            pos = idx + 1
    
    return references


def build_new_string_table(entries: List[StringEntry]) -> Tuple[bytes, Dict[int, int], List[int]]:
    """
    Build a new string table with translated text.
    
    Args:
        entries: List of string entries (sorted by offset)
        
    Returns:
        (new_string_table_bytes, offset_mapping, char_offsets)
        offset_mapping maps old offset to new byte offset
        char_offsets is list of character offsets for each string (for index table)
    """
    new_strings = []
    offset_mapping = {}
    char_offsets = []  # 字元偏移量列表 (用於更新索引表)
    current_byte_offset = 0
    current_char_offset = 0
    
    for entry in entries:
        old_offset = entry.offset
        
        # Use translated text if available, otherwise use original
        text = entry.translated if entry.translated else entry.original
        
        # Record character offset (for index table)
        char_offsets.append(current_char_offset)
        
        # Encode as UTF-16LE with null terminator
        encoded = text.encode('utf-16le') + b'\x00\x00'
        
        offset_mapping[old_offset] = current_byte_offset
        new_strings.append(encoded)
        
        current_byte_offset += len(encoded)
        current_char_offset += len(text) + 1  # +1 for null terminator
    
    return b''.join(new_strings), offset_mapping, char_offsets


def update_name_index_table(data: bytearray, char_offsets: List[int], 
                            name_count: int = 21) -> None:
    """
    更新角色名稱索引表
    
    索引表位於 0x68BC0，包含 name_count 個 32-bit 索引值
    每個索引值是對應字串在字串表中的字元偏移量
    
    Args:
        data: 檔案資料 (會被修改)
        char_offsets: 所有字串的字元偏移量列表
        name_count: 角色名稱數量 (預設 21)
    """
    index_table_offset = 0x68BC0
    
    # 更新前 name_count 個索引
    for i in range(min(name_count, len(char_offsets))):
        struct.pack_into('<I', data, index_table_offset + i * 4, char_offsets[i])


def import_translation(original_file: Path, json_file: Path, output_file: Path,
                       backup: bool = True):
    """
    Import translated text back into the script file.
    
    BSXScript 3.1 結構:
    - 0x00-0x10: Magic "BSXScript 3.1"
    - 0x10-0x30: Header
    - 0x30+: Section table
    - 0x68BC0: 角色名稱索引表 (21 個 32-bit 字元偏移量)
    - 0x68C18: 填充 (8 bytes)
    - 0x68C20: 字串表開始 (UTF-16LE)
    
    Args:
        original_file: Original bsxx.dat file
        json_file: JSON file with translations (from export_script.py)
        output_file: Output file path
        backup: Whether to create a backup of the original
    """
    # Constants
    INDEX_TABLE_OFFSET = 0x68BC0
    STRING_TABLE_OFFSET = 0x68C20  # 真正的字串表起始位置
    NAME_COUNT = 21  # 角色名稱數量
    
    # Create backup
    if backup and original_file.exists():
        backup_file = original_file.with_suffix('.dat.bak')
        if not backup_file.exists():
            shutil.copy2(original_file, backup_file)
            print(f"Created backup: {backup_file}")
    
    # Load original file
    with open(original_file, 'rb') as f:
        data = bytearray(f.read())
    
    # Load translation data
    script_info, entries = load_translation(json_file)
    
    if not entries:
        print("No translation entries found!")
        return
    
    print(f"Loaded {len(entries)} translation entries")
    print(f"String table offset: 0x{STRING_TABLE_OFFSET:X}")
    
    # Count how many entries have translations
    translated_count = sum(1 for e in entries if e.translated)
    print(f"Entries with translations: {translated_count} / {len(entries)}")
    
    # Build new string table and get character offsets
    new_string_table, offset_mapping, char_offsets = build_new_string_table(entries)
    print(f"New string table size: {len(new_string_table)} bytes")
    
    # Update name index table (0x68BC0)
    print(f"Updating name index table ({NAME_COUNT} entries at 0x{INDEX_TABLE_OFFSET:X})")
    for i in range(min(NAME_COUNT, len(char_offsets))):
        struct.pack_into('<I', data, INDEX_TABLE_OFFSET + i * 4, char_offsets[i])
    
    # Truncate at string table start and append new string table
    # 保留 0x00 到 0x68C20 (包括索引表和填充)
    new_data = bytes(data[:STRING_TABLE_OFFSET]) + new_string_table
    
    # Write output file
    with open(output_file, 'wb') as f:
        f.write(new_data)
    
    print(f"\nSuccessfully wrote: {output_file}")
    print(f"Original size: {len(data)} bytes")
    print(f"New size: {len(new_data)} bytes")
    print(f"Size difference: {len(new_data) - len(data):+d} bytes")


def validate_translation(json_file: Path):
    """
    Validate translation file and show statistics.
    """
    _, entries = load_translation(json_file)
    
    total = len(entries)
    translated = sum(1 for e in entries if e.translated)
    dialogs = sum(1 for e in entries if e.context == 'dialog')
    names = sum(1 for e in entries if e.context == 'name')
    
    print(f"Translation Statistics:")
    print(f"  Total entries: {total}")
    print(f"  Translated: {translated} ({translated/total*100:.1f}%)")
    print(f"  Dialogs: {dialogs}")
    print(f"  Names: {names}")
    print(f"  Other: {total - dialogs - names}")
    
    # Check for empty translations
    empty_dialogs = sum(1 for e in entries 
                        if e.context == 'dialog' and not e.translated)
    if empty_dialogs > 0:
        print(f"\n  Warning: {empty_dialogs} dialog entries have no translation")
    
    # Check for entries where translated == original
    unchanged = sum(1 for e in entries 
                    if e.translated and e.translated == e.original)
    if unchanged > 0:
        print(f"  Note: {unchanged} entries have identical original/translated text")


def main():
    parser = argparse.ArgumentParser(
        description='Import translated text into BSXScript 3.1 files'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import translations')
    import_parser.add_argument(
        'original',
        type=Path,
        help='Original bsxx.dat file'
    )
    import_parser.add_argument(
        'translation',
        type=Path,
        help='Translation JSON file'
    )
    import_parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output file (default: overwrite original)'
    )
    import_parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backup file'
    )
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate translation file')
    validate_parser.add_argument(
        'translation',
        type=Path,
        help='Translation JSON file to validate'
    )
    
    args = parser.parse_args()
    
    if args.command == 'import':
        if not args.original.exists():
            print(f"Error: Original file not found: {args.original}")
            return 1
        if not args.translation.exists():
            print(f"Error: Translation file not found: {args.translation}")
            return 1
        
        output_file = args.output if args.output else args.original
        
        try:
            import_translation(
                args.original, 
                args.translation, 
                output_file,
                backup=not args.no_backup
            )
            return 0
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    elif args.command == 'validate':
        if not args.translation.exists():
            print(f"Error: Translation file not found: {args.translation}")
            return 1
        
        try:
            validate_translation(args.translation)
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    exit(main())
