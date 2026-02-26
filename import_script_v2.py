#!/usr/bin/env python3
"""
BSXScript 3.1 Text Importer for Bishop Engine Games (v2)
Imports translated text from JSON back into bsxx.dat

正確處理以下結構：
- 0x68BC0 - 0x68C14: 角色名稱索引表 (21 x 4 bytes)
- 0x68C14 - 0x68C20: 填充區 (12 bytes)
- 0x68C20 - 0x68D0E: 角色名稱字串表 (21 strings)
- 0x68D10 - 0x6A210: 對話索引表 (1344 x 4 bytes)
- 0x6A210 - EOF: 對話字串表

Header 中的偏移量：
- 0x0090: 角色名稱字串表起始 (0x68C20)
- 0x0098: 對話索引表起始 (0x68D10)
- 0x00A0: 對話字串表起始 (0x6A210)

Author: GalTransl-BGI Project
"""

import struct
import json
import argparse
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# 原始結構常數
ORIG_NAME_INDEX_TABLE = 0x68BC0
ORIG_NAME_STRING_TABLE = 0x68C20
ORIG_DIALOG_INDEX_TABLE = 0x68D10
ORIG_DIALOG_STRING_TABLE = 0x6A210

NAME_COUNT = 21
DIALOG_INDEX_COUNT = 1344

# Header 中偏移量的位置
HEADER_NAME_STRING_OFFSET = 0x90
HEADER_DIALOG_INDEX_OFFSET = 0x98
HEADER_DIALOG_STRING_OFFSET = 0xA0


def load_translation(json_file: Path) -> Tuple[List[dict], List[dict]]:
    """
    Load translation data from JSON file.
    
    Returns:
        (name_entries, dialog_entries)
        
    每個 entry 包含: index, offset, original, translated, context
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    strings_data = data.get('strings', [])
    
    # 分離名稱和對話
    name_entries = []
    dialog_entries = []
    
    for s in strings_data:
        entry = {
            'index': s['index'],
            'offset': s['offset'],
            'original': s['original'],
            'translated': s.get('translated', ''),
            'context': s.get('context', 'other')
        }
        
        # 根據偏移量分類 (更準確)
        offset = s['offset']
        if ORIG_NAME_STRING_TABLE <= offset < ORIG_DIALOG_INDEX_TABLE:
            # 角色名稱區域，但需要過濾掉索引值被誤認的情況
            # 真正的名稱字串長度至少 >= 1 且不是單個控制字元
            if len(s['original']) >= 1:
                # 排除索引表被誤認的字串 (單字元且 ord < 0x100)
                if len(s['original']) == 1 and ord(s['original'][0]) < 0x100:
                    if offset >= ORIG_DIALOG_INDEX_TABLE - 0x10:
                        # 可能是索引表的一部分，跳過
                        continue
                name_entries.append(entry)
        elif offset >= ORIG_DIALOG_STRING_TABLE:
            dialog_entries.append(entry)
    
    # 確保排序
    name_entries.sort(key=lambda x: x['offset'])
    dialog_entries.sort(key=lambda x: x['offset'])
    
    return name_entries, dialog_entries


def build_name_string_table(entries: List[dict]) -> Tuple[bytes, List[int]]:
    """
    Build name string table.
    
    Returns:
        (string_table_bytes, char_offsets)
    """
    strings = []
    char_offsets = []
    current_char_offset = 0
    
    for entry in entries:
        text = entry['translated'] if entry['translated'] else entry['original']
        char_offsets.append(current_char_offset)
        
        encoded = text.encode('utf-16le') + b'\x00\x00'
        strings.append(encoded)
        
        current_char_offset += len(text) + 1  # +1 for null terminator
    
    return b''.join(strings), char_offsets


def build_dialog_string_table(entries: List[dict]) -> Tuple[bytes, List[int]]:
    """
    Build dialog string table.
    
    Returns:
        (string_table_bytes, char_offsets)
    """
    strings = []
    char_offsets = []
    current_char_offset = 0
    
    for entry in entries:
        text = entry['translated'] if entry['translated'] else entry['original']
        char_offsets.append(current_char_offset)
        
        encoded = text.encode('utf-16le') + b'\x00\x00'
        strings.append(encoded)
        
        current_char_offset += len(text) + 1  # +1 for null terminator
    
    return b''.join(strings), char_offsets


def import_translation(original_file: Path, json_file: Path, output_file: Path,
                       backup: bool = True):
    """
    Import translated text back into the script file.
    """
    # Create backup
    if backup and original_file.exists():
        backup_file = original_file.with_suffix('.dat.bak')
        if not backup_file.exists():
            shutil.copy2(original_file, backup_file)
            print(f"Created backup: {backup_file}")
    
    # Load original file
    with open(original_file, 'rb') as f:
        orig_data = f.read()
    
    # Load translation data
    name_entries, dialog_entries = load_translation(json_file)
    
    print(f"Loaded translations:")
    print(f"  Name entries: {len(name_entries)}")
    print(f"  Dialog entries: {len(dialog_entries)}")
    
    # Count translated
    name_translated = sum(1 for e in name_entries if e['translated'])
    dialog_translated = sum(1 for e in dialog_entries if e['translated'])
    print(f"  Translated names: {name_translated}/{len(name_entries)}")
    print(f"  Translated dialogs: {dialog_translated}/{len(dialog_entries)}")
    
    # Build new string tables
    name_table, name_char_offsets = build_name_string_table(name_entries)
    dialog_table, dialog_char_offsets = build_dialog_string_table(dialog_entries)
    
    print(f"\nNew string tables:")
    print(f"  Name table: {len(name_table)} bytes")
    print(f"  Dialog table: {len(dialog_table)} bytes")
    
    # 計算新的偏移量
    # 名稱字串表仍從 0x68C20 開始
    new_name_string_table = ORIG_NAME_STRING_TABLE
    
    # 計算名稱字串表結束位置，對齊到 0x10
    name_table_end = new_name_string_table + len(name_table)
    # 需要對齊並留出填充
    padding_needed = (0x10 - (name_table_end % 0x10)) % 0x10
    if padding_needed < 8:  # 確保至少 8 bytes 填充
        padding_needed += 0x10
    name_padding = b'\x00' * padding_needed
    
    # 新的對話索引表位置
    new_dialog_index_table = name_table_end + len(name_padding)
    
    # 對話索引表大小 (保持不變)
    dialog_index_table_size = DIALOG_INDEX_COUNT * 4
    
    # 新的對話字串表位置
    new_dialog_string_table = new_dialog_index_table + dialog_index_table_size
    
    print(f"\nNew offsets:")
    print(f"  Name string table: 0x{new_name_string_table:X}")
    print(f"  Dialog index table: 0x{new_dialog_index_table:X}")
    print(f"  Dialog string table: 0x{new_dialog_string_table:X}")
    
    # 開始建構新檔案
    output = bytearray(orig_data[:ORIG_NAME_INDEX_TABLE])  # 保留 header 和 code
    
    # 1. 寫入角色名稱索引表 (21 x 4 bytes)
    name_index_table = bytearray()
    for i in range(NAME_COUNT):
        if i < len(name_char_offsets):
            name_index_table.extend(struct.pack('<I', name_char_offsets[i]))
        else:
            name_index_table.extend(struct.pack('<I', 0))
    
    # 填充到 0x68C20 (12 bytes 填充)
    name_index_padding = b'\x00' * (ORIG_NAME_STRING_TABLE - ORIG_NAME_INDEX_TABLE - len(name_index_table))
    
    output.extend(name_index_table)
    output.extend(name_index_padding)
    
    # 2. 寫入名稱字串表
    output.extend(name_table)
    
    # 3. 填充對齊
    output.extend(name_padding)
    
    # 4. 寫入對話索引表
    # 讀取原始對話索引表並更新
    dialog_index_table = bytearray()
    
    # 建立原始偏移量到新字元偏移量的映射
    orig_dialog_offsets = [e['offset'] for e in dialog_entries]
    offset_to_new_char_offset = dict(zip(orig_dialog_offsets, dialog_char_offsets))
    
    for i in range(DIALOG_INDEX_COUNT):
        orig_idx = struct.unpack_from('<I', orig_data, ORIG_DIALOG_INDEX_TABLE + i * 4)[0]
        # 原始字元偏移量對應的位元組偏移量
        orig_byte_offset = ORIG_DIALOG_STRING_TABLE + orig_idx * 2
        
        # 找到對應的新字元偏移量
        if orig_byte_offset in offset_to_new_char_offset:
            new_char_offset = offset_to_new_char_offset[orig_byte_offset]
            dialog_index_table.extend(struct.pack('<I', new_char_offset))
        else:
            # 保持原始值（可能是最後一個特殊索引）
            dialog_index_table.extend(struct.pack('<I', orig_idx))
    
    output.extend(dialog_index_table)
    
    # 5. 寫入對話字串表
    output.extend(dialog_table)
    
    # 6. 更新 Header 中的偏移量
    struct.pack_into('<I', output, HEADER_NAME_STRING_OFFSET, new_name_string_table)
    struct.pack_into('<I', output, HEADER_DIALOG_INDEX_OFFSET, new_dialog_index_table)
    struct.pack_into('<I', output, HEADER_DIALOG_STRING_OFFSET, new_dialog_string_table)
    
    # Write output file
    with open(output_file, 'wb') as f:
        f.write(output)
    
    print(f"\nSuccessfully wrote: {output_file}")
    print(f"Original size: {len(orig_data)} bytes")
    print(f"New size: {len(output)} bytes")
    print(f"Size difference: {len(output) - len(orig_data):+d} bytes")


def validate_translation(json_file: Path):
    """Validate translation file and show statistics."""
    name_entries, dialog_entries = load_translation(json_file)
    
    total = len(name_entries) + len(dialog_entries)
    translated = (sum(1 for e in name_entries if e['translated']) + 
                  sum(1 for e in dialog_entries if e['translated']))
    
    print(f"Translation Statistics:")
    print(f"  Total entries: {total}")
    print(f"  Names: {len(name_entries)} ({sum(1 for e in name_entries if e['translated'])} translated)")
    print(f"  Dialogs: {len(dialog_entries)} ({sum(1 for e in dialog_entries if e['translated'])} translated)")
    print(f"  Total translated: {translated} ({translated/total*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description='Import translated text into BSXScript 3.1 files'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import translations')
    import_parser.add_argument('original', type=Path, help='Original bsxx.dat file')
    import_parser.add_argument('json', type=Path, help='Translation JSON file')
    import_parser.add_argument('-o', '--output', type=Path, default=None,
                               help='Output file (default: overwrite original)')
    import_parser.add_argument('--no-backup', action='store_true',
                               help='Do not create backup')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate translation file')
    validate_parser.add_argument('json', type=Path, help='Translation JSON file')
    
    args = parser.parse_args()
    
    if args.command == 'import':
        output = args.output or args.original
        import_translation(args.original, args.json, output, 
                          backup=not args.no_backup)
    elif args.command == 'validate':
        validate_translation(args.json)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
