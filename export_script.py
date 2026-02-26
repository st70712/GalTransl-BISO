#!/usr/bin/env python3
"""
BSXScript 3.1 Text Exporter for Bishop Engine Games
Exports text from bsxx.dat to JSON format for translation

File Structure:
- 0x00-0x10: Magic "BSXScript 3.1\x00\x00\x00"
- 0x10-0x30: Header fields
- 0x30+: Section table
- String table near end of file, UTF-16LE encoded

Author: GalTransl-BGI Project
"""

import struct
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple


@dataclass
class TextEntry:
    """Represents a text entry in the script"""
    index: int
    offset: int
    original: str
    translated: str = ""
    context: str = ""  # Additional context like speaker name
    

@dataclass
class ScriptInfo:
    """Script file metadata"""
    magic: str
    version: int
    entry_count: int
    section_count: int
    string_table_offset: int
    string_count: int


def find_string_table_offset(data: bytes) -> int:
    """
    Find the offset where the string table starts.
    The string table contains UTF-16LE encoded strings near the end of the file.
    """
    # Based on analysis, string table starts around 0x68BE0 for typical bsxx.dat
    # We search for the pattern of short strings followed by longer Japanese text
    
    # Get section info from header
    section_count = struct.unpack_from('<I', data, 0x28)[0]
    
    # Last section end + padding area
    # Section table starts at 0x30, each entry is 8 bytes (offset, size)
    last_section_offset = 0
    last_section_size = 0
    
    for i in range(section_count):
        offset = 0x30 + i * 8
        off, size = struct.unpack_from('<II', data, offset)
        if off + size > last_section_offset + last_section_size:
            last_section_offset = off
            last_section_size = size
    
    # String table typically starts after some index tables
    # Search for UTF-16LE string patterns after last section
    search_start = last_section_offset + last_section_size
    
    # Look for the first valid UTF-16LE Japanese character sequence
    for i in range(search_start, len(data) - 10, 2):
        # Try to decode as UTF-16LE
        try:
            sample = data[i:i+20].decode('utf-16le')
            # Check for Japanese characters
            if any('\u3040' <= c <= '\u9FFF' or '\uFF00' <= c <= '\uFFEF' for c in sample):
                # Backtrack to find the real start
                pos = i
                while pos > search_start:
                    pos -= 2
                    if data[pos:pos+2] == b'\x00\x00':
                        return pos + 2
                return i
        except:
            continue
    
    return search_start


def extract_strings(data: bytes, start_offset: int) -> List[Tuple[int, str]]:
    """
    Extract all UTF-16LE strings from the string table.
    
    Args:
        data: Full file data
        start_offset: Offset where string table begins
        
    Returns:
        List of (offset, string) tuples
    """
    strings = []
    pos = start_offset
    
    while pos < len(data) - 2:
        # Find null terminator (0x00 0x00)
        end = pos
        while end < len(data) - 1:
            if data[end] == 0 and data[end + 1] == 0:
                break
            end += 2
        
        if end > pos:
            try:
                s = data[pos:end].decode('utf-16le')
                if s:  # Non-empty string
                    strings.append((pos, s))
            except UnicodeDecodeError:
                pass
        
        pos = end + 2
    
    return strings


def categorize_strings(strings: List[Tuple[int, str]]) -> Tuple[List[TextEntry], List[TextEntry], List[TextEntry]]:
    """
    Categorize strings into names, dialogs, and other text.
    
    Returns:
        (names, dialogs, other)
    """
    names = []
    dialogs = []
    other = []
    
    for idx, (offset, text) in enumerate(strings):
        entry = TextEntry(index=idx, offset=offset, original=text)
        
        # Skip very short strings that are likely control codes
        if len(text) <= 1:
            other.append(entry)
            continue
        
        # Dialogs typically start with Japanese quotation marks
        if text.startswith('「') or text.startswith('『') or text.startswith('（'):
            dialogs.append(entry)
        # Character names are typically short (2-15 chars) without quotes
        elif 2 <= len(text) <= 15 and not any(c in text for c in '。、！？「」『』（）'):
            names.append(entry)
        # Narrative text is usually longer
        elif len(text) > 15:
            dialogs.append(entry)
        else:
            other.append(entry)
    
    return names, dialogs, other


def export_script(input_file: Path, output_dir: Path, split_categories: bool = False):
    """
    Export script text to JSON format.
    
    Args:
        input_file: Path to bsxx.dat
        output_dir: Output directory for JSON files
        split_categories: If True, create separate files for names/dialogs/other
    """
    with open(input_file, 'rb') as f:
        data = f.read()
    
    # Verify magic
    magic = data[:16]
    if not magic.startswith(b'BSXScript'):
        raise ValueError(f"Invalid file format. Expected BSXScript, got: {magic}")
    
    # Parse header
    version = struct.unpack_from('<I', data, 0x10)[0]
    entry_count = struct.unpack_from('<I', data, 0x20)[0]
    section_count = struct.unpack_from('<I', data, 0x28)[0]
    
    print(f"BSXScript version: {version:#x}")
    print(f"Entry count: {entry_count}")
    print(f"Section count: {section_count}")
    
    # Find string table
    str_table_offset = find_string_table_offset(data)
    print(f"String table offset: {str_table_offset:#x}")
    
    # Extract strings
    strings = extract_strings(data, str_table_offset)
    print(f"Total strings found: {len(strings)}")
    
    # Categorize
    names, dialogs, other = categorize_strings(strings)
    print(f"Names: {len(names)}, Dialogs: {len(dialogs)}, Other: {len(other)}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Script info
    script_info = ScriptInfo(
        magic=magic.decode('ascii', errors='replace').rstrip('\x00'),
        version=version,
        entry_count=entry_count,
        section_count=section_count,
        string_table_offset=str_table_offset,
        string_count=len(strings)
    )
    
    if split_categories:
        # Save separate files
        with open(output_dir / 'script_info.json', 'w', encoding='utf-8') as f:
            json.dump(asdict(script_info), f, ensure_ascii=False, indent=2)
        
        with open(output_dir / 'names.json', 'w', encoding='utf-8') as f:
            json.dump([asdict(e) for e in names], f, ensure_ascii=False, indent=2)
        
        with open(output_dir / 'dialogs.json', 'w', encoding='utf-8') as f:
            json.dump([asdict(e) for e in dialogs], f, ensure_ascii=False, indent=2)
        
        with open(output_dir / 'other.json', 'w', encoding='utf-8') as f:
            json.dump([asdict(e) for e in other], f, ensure_ascii=False, indent=2)
        
        print(f"\nExported to {output_dir}:")
        print(f"  - script_info.json")
        print(f"  - names.json ({len(names)} entries)")
        print(f"  - dialogs.json ({len(dialogs)} entries)")
        print(f"  - other.json ({len(other)} entries)")
    else:
        # Save single file with all strings
        all_entries = []
        for entry in names:
            entry.context = "name"
            all_entries.append(entry)
        for entry in dialogs:
            entry.context = "dialog"
            all_entries.append(entry)
        for entry in other:
            entry.context = "other"
            all_entries.append(entry)
        
        # Sort by offset for proper order
        all_entries.sort(key=lambda x: x.offset)
        
        output_data = {
            'info': asdict(script_info),
            'strings': [asdict(e) for e in all_entries]
        }
        
        output_file = output_dir / 'script.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\nExported to {output_file}")
        print(f"Total entries: {len(all_entries)}")


def main():
    parser = argparse.ArgumentParser(
        description='Export text from BSXScript 3.1 files for translation'
    )
    parser.add_argument(
        'input',
        type=Path,
        help='Input bsxx.dat file'
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=Path('exported'),
        help='Output directory (default: ./exported)'
    )
    parser.add_argument(
        '-s', '--split',
        action='store_true',
        help='Split output into separate files by category'
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    try:
        export_script(args.input, args.output, args.split)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
