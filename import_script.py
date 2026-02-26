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


def validate_translation(json_file: Path, context_filter: str = 'dialog',
                         output_file: Optional[Path] = None):
    """
    Validate translation file, show statistics, and output untranslated entries.

    Args:
        json_file: Translation JSON file path.
        context_filter: Context type to filter ('dialog', 'name', 'other', 'all').
                        Default is 'dialog'.
        output_file: Optional path to write untranslated entries as JSON.
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    strings_data = data.get('strings', [])

    # 統計各 context 類型
    stats: Dict[str, Dict[str, int]] = {}
    for s in strings_data:
        ctx = s.get('context', 'other')
        stats.setdefault(ctx, {'total': 0, 'translated': 0})
        stats[ctx]['total'] += 1
        if s.get('translated', ''):
            stats[ctx]['translated'] += 1

    total = sum(v['total'] for v in stats.values())
    translated = sum(v['translated'] for v in stats.values())

    print(f"Translation Statistics:")
    print(f"  Total entries: {total}")
    for ctx in sorted(stats.keys()):
        v = stats[ctx]
        pct = v['translated'] / v['total'] * 100 if v['total'] else 0
        print(f"  [{ctx}] {v['translated']}/{v['total']} ({pct:.1f}%)")
    print(f"  Overall: {translated}/{total} "
          f"({translated / total * 100:.1f}% translated)")

    # 過濾出未翻譯的條目
    if context_filter == 'all':
        untranslated = [s for s in strings_data if not s.get('translated', '')]
    else:
        untranslated = [s for s in strings_data
                        if s.get('context', 'other') == context_filter
                        and not s.get('translated', '')]

    print(f"\nUntranslated entries (context='{context_filter}'): {len(untranslated)}")

    if not untranslated:
        print("  All entries are translated!")
        return

    # 輸出到檔案
    if output_file:
        out_data = []
        for s in untranslated:
            out_data.append({
                'index': s['index'],
                'offset': s['offset'],
                'original': s['original'],
                'translated': '',
                'context': s.get('context', 'other'),
            })
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(out_data, f, ensure_ascii=False, indent=2)
        print(f"  Wrote {len(out_data)} untranslated entries to: {output_file}")
    else:
        # 輸出到 stdout，預覽前 20 條
        preview_count = min(20, len(untranslated))
        for s in untranslated[:preview_count]:
            idx = s['index']
            orig = s['original']
            display = orig[:60] + '...' if len(orig) > 60 else orig
            print(f"  [{idx:5d}] {display}")
        if len(untranslated) > preview_count:
            print(f"  ... and {len(untranslated) - preview_count} more.")
        print(f"\n  Tip: use -o <file.json> to export all untranslated entries.")


def _read_utf16le_string(data: bytes, offset: int) -> str:
    """從指定偏移量讀取 UTF-16LE null-terminated 字串"""
    end = offset
    while end < len(data) - 1:
        if data[end] == 0 and data[end + 1] == 0:
            break
        end += 2
    try:
        return data[offset:end].decode('utf-16le')
    except UnicodeDecodeError:
        return f"(decode error at 0x{offset:X})"


def check_structure(original_file: Path, translated_file: Path):
    """
    比對原始 bsxx.dat 與翻譯後檔案，檢查結構性錯誤。

    檢查項目：
      1. Magic Number 與 Header 完整性
      2. 代碼區是否被意外修改
      3. Header 偏移量指標的一致性
      4. 名稱索引表的有效性
      5. 對話索引表的有效性
      6. 字串可讀性抽樣驗證
    """
    with open(original_file, 'rb') as f:
        orig = f.read()
    with open(translated_file, 'rb') as f:
        trans = f.read()

    errors: List[str] = []
    warnings: List[str] = []

    sep = '=' * 60
    print(sep)
    print('BSXScript 結構性檢查報告')
    print(sep)

    # ── 1. Magic & Header ────────────────────────────────────
    print('\n【1. Magic Number 與 Header】')
    orig_magic = orig[:16]
    trans_magic = trans[:16]
    if orig_magic == trans_magic:
        magic_text = orig_magic.rstrip(b'\x00').decode('ascii', errors='replace')
        print(f'  ✓ Magic 一致: {magic_text}')
    else:
        errors.append('Magic Number 不一致')
        print(f'  ✗ Magic 不一致！原始={orig_magic}  翻譯={trans_magic}')

    # ── 2. 代碼區完整性 ──────────────────────────────────────
    print('\n【2. 代碼區完整性 (0x00000 - 0x68BC0)】')
    code_end = ORIG_NAME_INDEX_TABLE
    if orig[:code_end] == trans[:code_end]:
        print(f'  ✓ 代碼區完全相同 ({code_end:,} bytes)')
    else:
        diff_count = sum(1 for a, b in zip(orig[:code_end], trans[:code_end]) if a != b)
        errors.append(f'代碼區有 {diff_count} bytes 不同')
        print(f'  ✗ 代碼區有 {diff_count} bytes 不同！')
        # 定位第一處差異
        for i in range(code_end):
            if orig[i] != trans[i]:
                print(f'     第一處差異位於 0x{i:05X}: '
                      f'原始=0x{orig[i]:02X} 翻譯=0x{trans[i]:02X}')
                break

    # ── 3. Header 偏移量指標 ──────────────────────────────────
    print('\n【3. Header 偏移量指標】')
    ptr_defs = [
        (HEADER_NAME_STRING_OFFSET, '名稱字串表'),
        (HEADER_DIALOG_INDEX_OFFSET, '對話索引表'),
        (HEADER_DIALOG_STRING_OFFSET, '對話字串表'),
    ]
    trans_ptrs = {}
    for ptr_off, label in ptr_defs:
        orig_val = struct.unpack_from('<I', orig, ptr_off)[0]
        trans_val = struct.unpack_from('<I', trans, ptr_off)[0]
        trans_ptrs[label] = trans_val
        ok = trans_val < len(trans)
        status = '✓' if ok else '✗ 超出檔案範圍!'
        if not ok:
            errors.append(f'{label}偏移量 0x{trans_val:X} 超出檔案範圍')
        print(f'  {status} 0x{ptr_off:02X} {label}: '
              f'原始=0x{orig_val:05X}  翻譯=0x{trans_val:05X}')

    name_str_off = trans_ptrs['名稱字串表']
    dialog_idx_off = trans_ptrs['對話索引表']
    dialog_str_off = trans_ptrs['對話字串表']

    # 偏移量順序必須遞增
    if not (name_str_off < dialog_idx_off < dialog_str_off):
        errors.append('偏移量順序錯誤 (應為 名稱字串 < 對話索引 < 對話字串)')
        print('  ✗ 偏移量順序錯誤！')
    else:
        print('  ✓ 偏移量順序正確 (名稱字串 < 對話索引 < 對話字串)')

    # ── 4. 名稱索引表 ────────────────────────────────────────
    print('\n【4. 名稱索引表】')
    # 找出名稱索引表位置 (在翻譯檔案中仍然是 0x68BC0)
    name_idx_base = ORIG_NAME_INDEX_TABLE
    name_str_base = name_str_off

    # 計算名稱字串表結束位置 (= 對話索引表起始前的填充開始)
    name_str_region_end = dialog_idx_off

    name_ok = True
    for i in range(NAME_COUNT):
        char_idx = struct.unpack_from('<I', trans, name_idx_base + i * 4)[0]
        byte_off = name_str_base + char_idx * 2
        if byte_off >= name_str_region_end:
            errors.append(f'名稱索引 [{i}] 字元偏移={char_idx} 超出名稱字串區域')
            print(f'  ✗ 索引 [{i:2d}] 偏移={char_idx:3d} → 0x{byte_off:05X} 超出範圍!')
            name_ok = False
        else:
            name = _read_utf16le_string(trans, byte_off)
            if not name or name.startswith('(decode error'):
                errors.append(f'名稱索引 [{i}] 指向無效字串')
                print(f'  ✗ 索引 [{i:2d}] 偏移={char_idx:3d} → 無法讀取字串')
                name_ok = False
            else:
                print(f'  ✓ 索引 [{i:2d}] 偏移={char_idx:3d} → "{name}"')
    if name_ok:
        print(f'  ── {NAME_COUNT} 個名稱索引全部正確')

    # ── 5. 對話索引表 ────────────────────────────────────────
    print('\n【5. 對話索引表】')
    dialog_idx_count = (dialog_str_off - dialog_idx_off) // 4
    dialog_str_end = len(trans)

    if dialog_idx_count != DIALOG_INDEX_COUNT:
        warnings.append(f'對話索引數量 {dialog_idx_count} != 預期 {DIALOG_INDEX_COUNT}')
        print(f'  ⚠ 索引數量: {dialog_idx_count} (預期 {DIALOG_INDEX_COUNT})')
    else:
        print(f'  ✓ 索引數量: {dialog_idx_count}')

    invalid_idx = 0
    max_char_idx = 0
    for i in range(dialog_idx_count):
        char_idx = struct.unpack_from('<I', trans, dialog_idx_off + i * 4)[0]
        byte_off = dialog_str_off + char_idx * 2
        if char_idx > max_char_idx:
            max_char_idx = char_idx
        if byte_off >= dialog_str_end:
            invalid_idx += 1
            if invalid_idx <= 3:  # 只印前三個
                print(f'  ✗ 索引 [{i}] 偏移={char_idx} → 0x{byte_off:05X} 超出範圍!')

    if invalid_idx > 0:
        errors.append(f'{invalid_idx} 個對話索引超出字串表範圍')
        if invalid_idx > 3:
            print(f'  ... 還有 {invalid_idx - 3} 個超出範圍的索引')
    else:
        print(f'  ✓ 所有 {dialog_idx_count} 個索引都在有效範圍內')

    # 抽樣檢查：驗證首尾各5條對話可讀
    print('\n  抽樣驗證 (首尾各 5 條):')
    sample_indices = list(range(min(5, dialog_idx_count))) + \
                     list(range(max(0, dialog_idx_count - 5), dialog_idx_count))
    sample_indices = sorted(set(sample_indices))
    sample_ok = True
    for i in sample_indices:
        char_idx = struct.unpack_from('<I', trans, dialog_idx_off + i * 4)[0]
        byte_off = dialog_str_off + char_idx * 2
        if byte_off < dialog_str_end:
            text = _read_utf16le_string(trans, byte_off)
            display = text[:40] + '...' if len(text) > 40 else text
            print(f'    [{i:4d}] {display}')
            if not text or text.startswith('(decode error'):
                sample_ok = False
        else:
            sample_ok = False
            print(f'    [{i:4d}] (超出範圍)')

    if sample_ok:
        print('  ✓ 抽樣字串均可正常讀取')
    else:
        errors.append('部分抽樣對話無法正常讀取')
        print('  ✗ 部分抽樣字串無法讀取!')

    # ── 6. 檔案大小合理性 ────────────────────────────────────
    print('\n【6. 檔案大小】')
    print(f'  原始: {len(orig):,} bytes')
    print(f'  翻譯: {len(trans):,} bytes')
    diff = len(trans) - len(orig)
    ratio = abs(diff) / len(orig) * 100
    if ratio > 50:
        warnings.append(f'檔案大小差異過大 ({ratio:.1f}%)')
        print(f'  ⚠ 差異 {diff:+,} bytes ({ratio:.1f}%)，幅度較大')
    else:
        print(f'  ✓ 差異 {diff:+,} bytes ({ratio:.1f}%)')

    # ── 總結 ─────────────────────────────────────────────────
    print(f'\n{sep}')
    print('【檢查結果】')
    if not errors and not warnings:
        print('  ✓ 全部通過！翻譯檔案結構正確，不應影響遊戲執行。')
    else:
        if warnings:
            print(f'  ⚠ {len(warnings)} 個警告:')
            for w in warnings:
                print(f'    - {w}')
        if errors:
            print(f'  ✗ {len(errors)} 個錯誤 (可能導致遊戲異常):')
            for e in errors:
                print(f'    - {e}')
    print(sep)

    return len(errors) == 0


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
    validate_parser.add_argument('-c', '--context', type=str, default='dialog',
                                 choices=['dialog', 'name', 'other', 'all'],
                                 help='Context type to filter (default: dialog)')
    validate_parser.add_argument('-o', '--output', type=Path, default=None,
                                 help='Output untranslated entries to JSON file')
    
    # Check command
    check_parser = subparsers.add_parser(
        'check', help='Check translated file for structural errors')
    check_parser.add_argument('original', type=Path,
                              help='Original bsxx.dat file')
    check_parser.add_argument('translated', type=Path,
                              help='Translated bsxx.dat file')
    
    args = parser.parse_args()
    
    if args.command == 'import':
        output = args.output or args.original
        import_translation(args.original, args.json, output, 
                          backup=not args.no_backup)
    elif args.command == 'validate':
        validate_translation(args.json, context_filter=args.context,
                             output_file=args.output)
    elif args.command == 'check':
        ok = check_structure(args.original, args.translated)
        raise SystemExit(0 if ok else 1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
