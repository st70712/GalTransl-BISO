#!/usr/bin/env python3
"""
BSXScript 3.1 Text Importer for Bishop Engine Games (v3)
Imports translated text from JSON back into bsxx.dat

動態讀取檔案 Header 來決定結構參數，不使用硬編碼常數。

Header 結構 (offset, size pairs):
- 0x0080: 資料區起始偏移量
- 0x0088/0x008C: 角色名稱索引表 (offset / size)
- 0x0090/0x0094: 角色名稱字串表 (offset / size)
- 0x0098/0x009C: 對話索引表 (offset / size)
- 0x00A0/0x00A4: 對話字串表 (offset / size)

所有表格連續排列，中間無間隙：
  名稱索引表 → 名稱字串表 → 對話索引表 → 對話字串表

Author: GalTransl-BGI Project
"""

import struct
import json
import argparse
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# Header 中各欄位的位置
HEADER_DATA_AREA_OFFSET = 0x80
HEADER_NAME_INDEX_OFFSET = 0x88
HEADER_NAME_INDEX_SIZE = 0x8C
HEADER_NAME_STRING_OFFSET = 0x90
HEADER_NAME_STRING_SIZE = 0x94
HEADER_DIALOG_INDEX_OFFSET = 0x98
HEADER_DIALOG_INDEX_SIZE = 0x9C
HEADER_DIALOG_STRING_OFFSET = 0xA0
HEADER_DIALOG_STRING_SIZE = 0xA4


def read_file_structure(data: bytes) -> dict:
    """
    從檔案 Header 讀取實際結構參數。

    Returns:
        dict with keys:
            name_index_offset, name_index_size, name_count,
            name_string_offset, name_string_size,
            dialog_index_offset, dialog_index_size, dialog_index_count,
            dialog_string_offset, dialog_string_size
    """
    ni_off = struct.unpack_from('<I', data, HEADER_NAME_INDEX_OFFSET)[0]
    ni_size = struct.unpack_from('<I', data, HEADER_NAME_INDEX_SIZE)[0]
    ns_off = struct.unpack_from('<I', data, HEADER_NAME_STRING_OFFSET)[0]
    ns_size = struct.unpack_from('<I', data, HEADER_NAME_STRING_SIZE)[0]
    di_off = struct.unpack_from('<I', data, HEADER_DIALOG_INDEX_OFFSET)[0]
    di_size = struct.unpack_from('<I', data, HEADER_DIALOG_INDEX_SIZE)[0]
    ds_off = struct.unpack_from('<I', data, HEADER_DIALOG_STRING_OFFSET)[0]
    ds_size = struct.unpack_from('<I', data, HEADER_DIALOG_STRING_SIZE)[0]

    return {
        'name_index_offset': ni_off,
        'name_index_size': ni_size,
        'name_count': ni_size // 4,
        'name_string_offset': ns_off,
        'name_string_size': ns_size,
        'dialog_index_offset': di_off,
        'dialog_index_size': di_size,
        'dialog_index_count': di_size // 4,
        'dialog_string_offset': ds_off,
        'dialog_string_size': ds_size,
    }


def load_translation(json_file: Path, fs: dict) -> Tuple[List[dict], List[dict]]:
    """
    Load translation data from JSON file.

    根據原始檔案結構的實際偏移量來分類字串。

    Args:
        json_file: 翻譯 JSON 檔案路徑
        fs: read_file_structure() 回傳的結構參數

    Returns:
        (name_entries, dialog_entries)

    每個 entry 包含: index, offset, original, translated, context
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    strings_data = data.get('strings', [])

    ns_off = fs['name_string_offset']
    ns_end = ns_off + fs['name_string_size']
    ds_off = fs['dialog_string_offset']
    ds_end = ds_off + fs['dialog_string_size']

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

        offset = s['offset']
        if ns_off <= offset < ns_end:
            # 角色名稱字串區域
            name_entries.append(entry)
        elif ds_off <= offset < ds_end:
            # 對話字串區域
            dialog_entries.append(entry)
        # else: 在索引表或其他區域的條目，跳過（可能是 export 掃描到的偽字串）

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

    動態讀取原始檔案的 Header 來決定所有結構偏移量。
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

    # 動態讀取檔案結構
    fs = read_file_structure(orig_data)

    print(f"Original file structure:")
    print(f"  Name index table:  0x{fs['name_index_offset']:X} "
          f"({fs['name_count']} entries, {fs['name_index_size']} bytes)")
    print(f"  Name string table: 0x{fs['name_string_offset']:X} "
          f"({fs['name_string_size']} bytes)")
    print(f"  Dialog index table: 0x{fs['dialog_index_offset']:X} "
          f"({fs['dialog_index_count']} entries, {fs['dialog_index_size']} bytes)")
    print(f"  Dialog string table: 0x{fs['dialog_string_offset']:X} "
          f"({fs['dialog_string_size']} bytes)")

    # Load translation data (使用實際偏移量分類)
    name_entries, dialog_entries = load_translation(json_file, fs)

    print(f"\nLoaded translations:")
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

    # ── 建構新檔案 ──────────────────────────────────────────

    # 保留從檔案開頭到名稱索引表之前的所有資料（header + code）
    orig_name_index_offset = fs['name_index_offset']
    output = bytearray(orig_data[:orig_name_index_offset])

    # 1. 重建名稱索引表
    #    建立原始位元組偏移量 -> 新字元偏移量的映射
    orig_name_byte_offsets = [e['offset'] for e in name_entries]
    name_offset_map = dict(zip(orig_name_byte_offsets, name_char_offsets))

    name_count = fs['name_count']
    orig_ns_off = fs['name_string_offset']

    name_index_table = bytearray()
    for i in range(name_count):
        orig_char_idx = struct.unpack_from('<I', orig_data,
                                           orig_name_index_offset + i * 4)[0]
        # 計算原始位元組偏移量
        orig_byte_off = orig_ns_off + orig_char_idx * 2

        if orig_byte_off in name_offset_map:
            new_char_offset = name_offset_map[orig_byte_off]
        else:
            # 保持原始字元偏移量（不應該發生，但作為安全措施）
            new_char_offset = orig_char_idx
        name_index_table.extend(struct.pack('<I', new_char_offset))

    output.extend(name_index_table)

    # 2. 名稱字串表（緊接名稱索引表之後，原始檔案中無間隙）
    new_name_string_offset = len(output)
    output.extend(name_table)

    # 3. 對話索引表
    #    建立原始位元組偏移量 -> 新字元偏移量的映射
    orig_dialog_byte_offsets = [e['offset'] for e in dialog_entries]
    dialog_offset_map = dict(zip(orig_dialog_byte_offsets, dialog_char_offsets))

    dialog_index_count = fs['dialog_index_count']
    orig_di_off = fs['dialog_index_offset']
    orig_ds_off = fs['dialog_string_offset']

    new_dialog_index_offset = len(output)
    dialog_index_table = bytearray()
    unmapped_count = 0

    for i in range(dialog_index_count):
        orig_char_idx = struct.unpack_from('<I', orig_data,
                                           orig_di_off + i * 4)[0]
        # 計算原始位元組偏移量
        orig_byte_off = orig_ds_off + orig_char_idx * 2

        if orig_byte_off in dialog_offset_map:
            new_char_offset = dialog_offset_map[orig_byte_off]
        else:
            # 找不到映射 — 保持原始值
            new_char_offset = orig_char_idx
            unmapped_count += 1
        dialog_index_table.extend(struct.pack('<I', new_char_offset))

    output.extend(dialog_index_table)

    if unmapped_count > 0:
        print(f"\n  WARNING: {unmapped_count} dialog index entries could not be mapped")

    # 4. 對話字串表
    new_dialog_string_offset = len(output)
    output.extend(dialog_table)

    # 5. 更新 Header 中的所有偏移量和大小

    # 名稱索引表（位置不變，大小不變）
    struct.pack_into('<I', output, HEADER_NAME_INDEX_OFFSET, orig_name_index_offset)
    struct.pack_into('<I', output, HEADER_NAME_INDEX_SIZE, name_count * 4)

    # 名稱字串表
    struct.pack_into('<I', output, HEADER_NAME_STRING_OFFSET, new_name_string_offset)
    struct.pack_into('<I', output, HEADER_NAME_STRING_SIZE, len(name_table))

    # 對話索引表
    struct.pack_into('<I', output, HEADER_DIALOG_INDEX_OFFSET, new_dialog_index_offset)
    struct.pack_into('<I', output, HEADER_DIALOG_INDEX_SIZE, dialog_index_count * 4)

    # 對話字串表
    struct.pack_into('<I', output, HEADER_DIALOG_STRING_OFFSET, new_dialog_string_offset)
    struct.pack_into('<I', output, HEADER_DIALOG_STRING_SIZE, len(dialog_table))

    # 更新資料區起始偏移量 (0x80)
    struct.pack_into('<I', output, HEADER_DATA_AREA_OFFSET, orig_name_index_offset)

    print(f"\nNew offsets:")
    print(f"  Name index table:   0x{orig_name_index_offset:X} ({name_count * 4} bytes)")
    print(f"  Name string table:  0x{new_name_string_offset:X} ({len(name_table)} bytes)")
    print(f"  Dialog index table: 0x{new_dialog_index_offset:X} "
          f"({dialog_index_count * 4} bytes)")
    print(f"  Dialog string table: 0x{new_dialog_string_offset:X} "
          f"({len(dialog_table)} bytes)")

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

    從兩個檔案的 Header 動態讀取結構參數。

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

    orig_fs = read_file_structure(orig)
    trans_fs = read_file_structure(trans)

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
    # 代碼區 = 從檔案開頭到名稱索引表之前
    code_end = orig_fs['name_index_offset']
    trans_code_end = trans_fs['name_index_offset']

    print(f'\n【2. 代碼區完整性 (0x00000 - 0x{code_end:X})】')

    if code_end != trans_code_end:
        errors.append(f'名稱索引表位置不同 (原始=0x{code_end:X} 翻譯=0x{trans_code_end:X})')
        print(f'  ✗ 名稱索引表位置不同！原始=0x{code_end:X} 翻譯=0x{trans_code_end:X}')
    else:
        # 排除 header 偏移量欄位 (0x80-0xA7) 的差異，因為這些是預期會變更的
        header_region = set(range(0x80, 0xA8))
        diff_count = 0
        first_diff = None

        for i in range(min(code_end, len(trans))):
            if i in header_region:
                continue
            if i < len(orig) and i < len(trans) and orig[i] != trans[i]:
                diff_count += 1
                if first_diff is None:
                    first_diff = i

        if diff_count == 0:
            print(f'  ✓ 代碼區完全相同 ({code_end:,} bytes，排除 header 偏移量欄位)')
        else:
            errors.append(f'代碼區有 {diff_count} bytes 不同 (排除 header)')
            print(f'  ✗ 代碼區有 {diff_count} bytes 不同！')
            if first_diff is not None:
                print(f'     第一處差異位於 0x{first_diff:05X}: '
                      f'原始=0x{orig[first_diff]:02X} 翻譯=0x{trans[first_diff]:02X}')

    # ── 3. Header 偏移量指標 ──────────────────────────────────
    print('\n【3. Header 偏移量指標】')
    ptr_defs = [
        (HEADER_NAME_INDEX_OFFSET, HEADER_NAME_INDEX_SIZE, '名稱索引表'),
        (HEADER_NAME_STRING_OFFSET, HEADER_NAME_STRING_SIZE, '名稱字串表'),
        (HEADER_DIALOG_INDEX_OFFSET, HEADER_DIALOG_INDEX_SIZE, '對話索引表'),
        (HEADER_DIALOG_STRING_OFFSET, HEADER_DIALOG_STRING_SIZE, '對話字串表'),
    ]
    for ptr_off, size_off, label in ptr_defs:
        orig_val = struct.unpack_from('<I', orig, ptr_off)[0]
        trans_val = struct.unpack_from('<I', trans, ptr_off)[0]
        orig_sz = struct.unpack_from('<I', orig, size_off)[0]
        trans_sz = struct.unpack_from('<I', trans, size_off)[0]
        ok = trans_val < len(trans) and (trans_val + trans_sz) <= len(trans)
        status = '✓' if ok else '✗ 超出檔案範圍!'
        if not ok:
            errors.append(f'{label}偏移量 0x{trans_val:X}+{trans_sz} 超出檔案範圍')
        print(f'  {status} {label}: '
              f'原始=0x{orig_val:05X}({orig_sz:,}B)  '
              f'翻譯=0x{trans_val:05X}({trans_sz:,}B)')

    name_idx_off = trans_fs['name_index_offset']
    name_str_off = trans_fs['name_string_offset']
    dialog_idx_off = trans_fs['dialog_index_offset']
    dialog_str_off = trans_fs['dialog_string_offset']

    # 偏移量順序必須遞增
    if not (name_idx_off <= name_str_off <= dialog_idx_off <= dialog_str_off):
        errors.append('偏移量順序錯誤')
        print('  ✗ 偏移量順序錯誤！')
    else:
        print('  ✓ 偏移量順序正確 (名稱索引 ≤ 名稱字串 ≤ 對話索引 ≤ 對話字串)')

    # ── 4. 名稱索引表 ────────────────────────────────────────
    print('\n【4. 名稱索引表】')
    name_count = trans_fs['name_count']
    name_str_size = trans_fs['name_string_size']

    if name_count != orig_fs['name_count']:
        warnings.append(f'名稱數量不同: 原始={orig_fs["name_count"]} 翻譯={name_count}')
        print(f'  ⚠ 名稱數量: {name_count} (原始 {orig_fs["name_count"]})')
    else:
        print(f'  ✓ 名稱數量: {name_count}')

    name_ok = True
    for i in range(name_count):
        idx_pos = name_idx_off + i * 4
        if idx_pos + 4 > len(trans):
            errors.append(f'名稱索引 [{i}] 超出檔案範圍')
            name_ok = False
            continue
        char_idx = struct.unpack_from('<I', trans, idx_pos)[0]
        byte_off = name_str_off + char_idx * 2
        if byte_off >= name_str_off + name_str_size:
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
        print(f'  ── {name_count} 個名稱索引全部正確')

    # ── 5. 對話索引表 ────────────────────────────────────────
    print('\n【5. 對話索引表】')
    dialog_idx_count = trans_fs['dialog_index_count']
    dialog_str_size = trans_fs['dialog_string_size']
    dialog_str_end = dialog_str_off + dialog_str_size

    if dialog_idx_count != orig_fs['dialog_index_count']:
        warnings.append(f'對話索引數量不同: 原始={orig_fs["dialog_index_count"]} '
                        f'翻譯={dialog_idx_count}')
        print(f'  ⚠ 索引數量: {dialog_idx_count} '
              f'(原始 {orig_fs["dialog_index_count"]})')
    else:
        print(f'  ✓ 索引數量: {dialog_idx_count}')

    invalid_idx = 0
    max_char_idx = 0
    for i in range(dialog_idx_count):
        idx_pos = dialog_idx_off + i * 4
        if idx_pos + 4 > len(trans):
            invalid_idx += 1
            continue
        char_idx = struct.unpack_from('<I', trans, idx_pos)[0]
        byte_off = dialog_str_off + char_idx * 2
        if char_idx > max_char_idx:
            max_char_idx = char_idx
        if byte_off >= dialog_str_end:
            invalid_idx += 1
            if invalid_idx <= 3:
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
        idx_pos = dialog_idx_off + i * 4
        if idx_pos + 4 > len(trans):
            sample_ok = False
            print(f'    [{i:4d}] (索引位置超出範圍)')
            continue
        char_idx = struct.unpack_from('<I', trans, idx_pos)[0]
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
