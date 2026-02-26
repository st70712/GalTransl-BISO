#!/usr/bin/env python3
"""
BSXScript 差異檢查工具
比較原始檔案和翻譯檔案之間的差異，找出潛在問題

Author: GalTransl-BGI Project
"""

import struct
import argparse
from pathlib import Path
from typing import List, Tuple, Dict


def extract_strings(data: bytes, str_start: int) -> List[Tuple[int, str]]:
    """從檔案中提取所有字串"""
    strings = []
    pos = str_start
    while pos < len(data) - 2:
        end = pos
        while end < len(data) - 1:
            if data[end] == 0 and data[end+1] == 0:
                break
            end += 2
        if end > pos:
            try:
                s = data[pos:end].decode('utf-16le')
                if s:
                    strings.append((pos, s))
            except:
                pass
        pos = end + 2
    return strings


def find_string_references(data: bytes, str_table_start: int) -> Dict[int, List[int]]:
    """
    在 bytecode 中搜尋所有字串偏移量引用
    返回: {字串偏移量: [引用位置列表]}
    """
    references = {}
    
    # 搜尋 bytecode 區域 (0x00 到字串表開始)
    for pos in range(0, str_table_start - 4):
        # 讀取 4 byte 作為潛在的偏移量
        offset = struct.unpack_from('<I', data, pos)[0]
        
        # 檢查是否指向字串表區域
        if str_table_start <= offset < len(data):
            if offset not in references:
                references[offset] = []
            references[offset].append(pos)
    
    return references


def analyze_file(filepath: Path) -> dict:
    """分析單個檔案"""
    with open(filepath, 'rb') as f:
        data = f.read()
    
    info = {
        'path': str(filepath),
        'size': len(data),
        'magic': data[:16].decode('ascii', errors='replace').rstrip('\x00'),
    }
    
    # Header
    info['version'] = struct.unpack_from('<I', data, 0x10)[0]
    info['entry_count'] = struct.unpack_from('<I', data, 0x20)[0]
    info['section_count'] = struct.unpack_from('<I', data, 0x28)[0]
    
    # Section table
    sections = []
    for i in range(info['section_count']):
        offset = 0x30 + i * 8
        off, size = struct.unpack_from('<II', data, offset)
        sections.append({'offset': off, 'size': size})
    info['sections'] = sections
    
    # 找到字串表起始位置
    # 從最後一個 section 之後開始搜尋
    last_section_end = max(s['offset'] + s['size'] for s in sections)
    
    # 搜尋第一個有效的 UTF-16LE 字串
    str_start = None
    for i in range(last_section_end, len(data) - 10, 2):
        try:
            # 嘗試解碼
            sample = data[i:i+20].decode('utf-16le')
            if len(sample) > 0 and sample[0].isprintable():
                str_start = i
                break
        except:
            continue
    
    if str_start is None:
        str_start = 0x68C14  # 預設值
    
    info['string_table_offset'] = str_start
    info['strings'] = extract_strings(data, str_start)
    info['data'] = data
    
    return info


def check_name_index_table(orig_data: bytes, trans_data: bytes) -> dict:
    """
    檢查角色名稱索引表是否正確更新
    
    索引表位於 0x68BC0，包含21個角色名稱的字元偏移量
    字串表起始於 0x68C20
    """
    result = {
        'index_table_offset': 0x68BC0,
        'string_table_offset': 0x68C20,
        'issues': [],
        'orig_indices': [],
        'trans_indices': [],
        'orig_names': [],
        'trans_names': [],
    }
    
    index_table_start = 0x68BC0
    str_table_start = 0x68C20
    
    # 讀取索引 (21個 + 結束標記)
    for i in range(21):
        orig_idx = struct.unpack_from('<I', orig_data, index_table_start + i*4)[0]
        trans_idx = struct.unpack_from('<I', trans_data, index_table_start + i*4)[0]
        result['orig_indices'].append(orig_idx)
        result['trans_indices'].append(trans_idx)
        
        # 讀取原始字串
        byte_offset = str_table_start + orig_idx * 2
        end = byte_offset
        while end < len(orig_data) - 1:
            if orig_data[end] == 0 and orig_data[end+1] == 0:
                break
            end += 2
        try:
            orig_name = orig_data[byte_offset:end].decode('utf-16le')
        except:
            orig_name = "(error)"
        result['orig_names'].append(orig_name)
        
        # 讀取翻譯字串 (使用相同索引)
        byte_offset = str_table_start + trans_idx * 2
        end = byte_offset
        while end < len(trans_data) - 1:
            if trans_data[end] == 0 and trans_data[end+1] == 0:
                break
            end += 2
        try:
            trans_name = trans_data[byte_offset:end].decode('utf-16le')
        except:
            trans_name = "(error)"
        result['trans_names'].append(trans_name)
    
    # 檢查索引是否匹配
    if result['orig_indices'] == result['trans_indices']:
        # 索引相同，但如果字串長度改變了，這就是問題
        # 計算原始和翻譯的累計長度
        orig_cumulative = 0
        trans_cumulative = 0
        for i, (orig_name, trans_name) in enumerate(zip(result['orig_names'], result['trans_names'])):
            orig_len = len(orig_name) + 1  # +1 for null terminator
            trans_len = len(trans_name) + 1
            
            if orig_cumulative != trans_cumulative and i > 0:
                result['issues'].append(
                    f"索引 {i} 偏移量不正確: 預期 {trans_cumulative}, 實際 {result['trans_indices'][i]}"
                )
            
            orig_cumulative += orig_len
            trans_cumulative += trans_len
    
    return result


def compare_files(orig_path: Path, trans_path: Path, verbose: bool = False):
    """比較兩個檔案"""
    print("=" * 60)
    print("BSXScript 差異檢查工具")
    print("=" * 60)
    
    orig = analyze_file(orig_path)
    trans = analyze_file(trans_path)
    
    # 基本資訊比較
    print("\n【基本資訊】")
    print(f"{'項目':<20} {'原始檔案':<20} {'翻譯檔案':<20} {'狀態':<10}")
    print("-" * 70)
    
    checks = [
        ('檔案大小', f"{orig['size']:,}", f"{trans['size']:,}", 
         '⚠ 不同' if orig['size'] != trans['size'] else '✓ 相同'),
        ('Magic', orig['magic'], trans['magic'],
         '✓ 相同' if orig['magic'] == trans['magic'] else '✗ 錯誤'),
        ('Version', f"0x{orig['version']:X}", f"0x{trans['version']:X}",
         '✓ 相同' if orig['version'] == trans['version'] else '✗ 錯誤'),
        ('Entry count', str(orig['entry_count']), str(trans['entry_count']),
         '✓ 相同' if orig['entry_count'] == trans['entry_count'] else '✗ 錯誤'),
        ('Section count', str(orig['section_count']), str(trans['section_count']),
         '✓ 相同' if orig['section_count'] == trans['section_count'] else '✗ 錯誤'),
        ('字串數量', str(len(orig['strings'])), str(len(trans['strings'])),
         '✓ 相同' if len(orig['strings']) == len(trans['strings']) else '✗ 錯誤'),
    ]
    
    for item, o_val, t_val, status in checks:
        print(f"{item:<20} {o_val:<20} {t_val:<20} {status:<10}")
    
    # Section table 比較
    print("\n【Section Table 比較】")
    sections_match = True
    for i, (o_sec, t_sec) in enumerate(zip(orig['sections'], trans['sections'])):
        if o_sec != t_sec:
            sections_match = False
            print(f"  Section {i}: 原始=0x{o_sec['offset']:X}+0x{o_sec['size']:X}, "
                  f"翻譯=0x{t_sec['offset']:X}+0x{t_sec['size']:X} ✗")
    if sections_match:
        print("  所有 Section 偏移量相同 ✓")
    
    # 字串順序檢查
    print("\n【字串順序檢查】")
    order_issues = []
    for i, (o_str, t_str) in enumerate(zip(orig['strings'], trans['strings'])):
        o_off, o_text = o_str
        t_off, t_text = t_str
        
        # 檢查是否為翻譯對 (原文應該對應翻譯)
        # 如果原文和翻譯文本完全不同且不是翻譯關係，記錄問題
        if o_text != t_text:
            # 這是預期的翻譯
            pass
        
    print(f"  字串數量匹配: {len(orig['strings'])} vs {len(trans['strings'])}")
    
    # 檢查字串偏移量引用
    print("\n【字串偏移量引用檢查】")
    orig_str_offsets = {off for off, _ in orig['strings']}
    trans_str_offsets = {off for off, _ in trans['strings']}
    
    # 找出原始檔案中對字串的引用
    orig_refs = find_string_references(orig['data'], orig['string_table_offset'])
    trans_refs = find_string_references(trans['data'], trans['string_table_offset'])
    
    # 統計有效引用
    valid_orig_refs = {off: locs for off, locs in orig_refs.items() if off in orig_str_offsets}
    valid_trans_refs = {off: locs for off, locs in trans_refs.items() if off in trans_str_offsets}
    
    print(f"  原始檔案中的字串引用: {sum(len(v) for v in valid_orig_refs.values())} 處")
    print(f"  翻譯檔案中的字串引用: {sum(len(v) for v in valid_trans_refs.values())} 處")
    
    # 檢查翻譯檔案中是否還有指向原始偏移量的引用 (這是錯誤的)
    print("\n【關鍵問題檢查】")
    
    # 建立原始偏移量到翻譯偏移量的映射
    orig_to_trans_offset = {}
    for i, ((o_off, o_text), (t_off, t_text)) in enumerate(zip(orig['strings'], trans['strings'])):
        orig_to_trans_offset[o_off] = t_off
    
    # 檢查翻譯檔案的 bytecode 是否還引用原始偏移量
    bad_refs = []
    for pos in range(0, trans['string_table_offset'] - 4):
        offset = struct.unpack_from('<I', trans['data'], pos)[0]
        # 如果偏移量指向原始字串表範圍，但不在翻譯字串表範圍
        if offset in orig_str_offsets and offset not in trans_str_offsets:
            bad_refs.append((pos, offset))
    
    if bad_refs:
        print(f"  ✗ 發現 {len(bad_refs)} 處未更新的字串引用！")
        if verbose:
            print("  前10個問題引用:")
            for pos, off in bad_refs[:10]:
                # 找對應的原始字串
                for o_off, o_text in orig['strings']:
                    if o_off == off:
                        print(f"    位置 0x{pos:06X} -> 原始偏移 0x{off:06X}: {o_text[:30]}")
                        break
    else:
        print("  ✓ 所有字串引用已正確更新")
    
    # 字串內容對比
    if verbose:
        print("\n【字串內容對比 (前30個)】")
        print(f"{'索引':^5} | {'原始偏移':^10} | {'翻譯偏移':^10} | {'原始文本':^25} | {'翻譯文本':^25}")
        print("-" * 100)
        
        for i in range(min(30, len(orig['strings']), len(trans['strings']))):
            o_off, o_text = orig['strings'][i]
            t_off, t_text = trans['strings'][i]
            o_short = (o_text[:22] + '...') if len(o_text) > 22 else o_text
            t_short = (t_text[:22] + '...') if len(t_text) > 22 else t_text
            
            marker = '' if o_text == t_text else '*'
            print(f"{i:^5} | 0x{o_off:06X}   | 0x{t_off:06X}   | {o_short:<25} | {t_short:<25} {marker}")
    
    # 總結
    print("\n" + "=" * 60)
    print("【診斷總結】")
    
    issues = []
    if orig['size'] != trans['size']:
        issues.append("檔案大小不同 (正常，因為翻譯文本長度不同)")
    if len(bad_refs) > 0:
        issues.append(f"發現 {len(bad_refs)} 處未更新的字串偏移量引用 (嚴重)")
    if len(orig['strings']) != len(trans['strings']):
        issues.append("字串數量不匹配 (嚴重)")
    
    if not issues:
        print("✓ 未發現明顯問題")
    else:
        for issue in issues:
            print(f"⚠ {issue}")
    
    # 如果有嚴重問題，提供建議
    if len(bad_refs) > 0:
        print("\n【建議】")
        print("字串偏移量引用未正確更新會導致遊戲讀取錯誤的文本。")
        print("這通常是因為 import_script.py 沒有正確找到並更新所有引用。")
        print("需要改進導入工具的偏移量更新邏輯。")
    
    # 檢查角色名稱索引表
    print("\n【角色名稱索引表檢查】")
    name_check = check_name_index_table(orig['data'], trans['data'])
    
    print(f"  索引表位置: 0x{name_check['index_table_offset']:X}")
    print(f"  字串表位置: 0x{name_check['string_table_offset']:X}")
    print(f"  角色名稱數量: {len(name_check['orig_names'])}")
    
    if verbose:
        print("\n  角色名稱對照:")
        print(f"  {'索引':^4} | {'原始索引':^8} | {'翻譯索引':^8} | {'原始名稱':^15} | {'翻譯名稱':^15} | 狀態")
        print("  " + "-" * 75)
        for i in range(len(name_check['orig_names'])):
            orig_idx = name_check['orig_indices'][i]
            trans_idx = name_check['trans_indices'][i]
            orig_name = name_check['orig_names'][i]
            trans_name = name_check['trans_names'][i]
            
            # 檢查名稱是否對應正確
            status = "✓" if orig_name == trans_name or trans_name else "⚠"
            print(f"  {i:^4} | {orig_idx:^8} | {trans_idx:^8} | {orig_name:<15} | {trans_name:<15} | {status}")
    
    # 計算預期的翻譯索引
    print("\n  索引正確性檢查:")
    expected_indices = [0]
    cumulative = 0
    for name in name_check['trans_names'][:-1]:  # 排除最後一個
        cumulative += len(name) + 1  # +1 for null terminator
        expected_indices.append(cumulative)
    
    index_mismatch = False
    for i, (expected, actual) in enumerate(zip(expected_indices, name_check['trans_indices'])):
        if expected != actual:
            index_mismatch = True
            if i < 5 or verbose:
                print(f"    索引[{i}]: 預期={expected}, 實際={actual} ✗")
    
    if index_mismatch:
        print("\n  ✗ 索引表未正確更新！這會導致角色名稱顯示錯誤。")
        print("  【解決方案】需要在導入時重新計算並更新索引表。")
    else:
        print("  ✓ 索引表正確")


def main():
    parser = argparse.ArgumentParser(
        description='BSXScript 差異檢查工具 - 比較原始和翻譯檔案'
    )
    parser.add_argument(
        'original',
        type=Path,
        help='原始 bsxx.dat 檔案'
    )
    parser.add_argument(
        'translated',
        type=Path,
        help='翻譯後的 bsxx.dat 檔案'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='顯示詳細資訊'
    )
    
    args = parser.parse_args()
    
    if not args.original.exists():
        print(f"錯誤: 找不到原始檔案 {args.original}")
        return 1
    if not args.translated.exists():
        print(f"錯誤: 找不到翻譯檔案 {args.translated}")
        return 1
    
    compare_files(args.original, args.translated, args.verbose)
    return 0


if __name__ == '__main__':
    exit(main())
