#!/usr/bin/env python3
"""
BSA Archive Extractor
Based on GARbro's ArcBSA.cs implementation
Supports Bishop BSA archives (version 1-3)
"""

import os
import struct
import argparse
from pathlib import Path
from typing import List, Tuple, Optional


class BsaEntry:
    """Represents a file entry in BSA archive"""
    def __init__(self, name: str, offset: int, size: int):
        self.name = name
        self.offset = offset
        self.size = size
    
    def __repr__(self):
        return f"BsaEntry(name='{self.name}', offset=0x{self.offset:X}, size={self.size})"


class BsaArchive:
    """BSA Archive reader based on GARbro's implementation"""
    
    # Signature: 'BSAr' (0x72415342)
    SIGNATURE = b'BSAr'
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.entries: List[BsaEntry] = []
        self.version = 0
        self._file_size = 0
        
    def open(self) -> bool:
        """Open and parse the BSA archive"""
        with open(self.filepath, 'rb') as f:
            # Read header
            signature = f.read(4)
            if signature != self.SIGNATURE:
                print(f"Error: Invalid signature. Expected 'BSAr', got {signature}")
                return False
            
            # Check 'c' at offset 4 (as Int16)
            magic_c = struct.unpack('<H', f.read(2))[0]
            if magic_c != ord('c'):
                print(f"Error: Expected 'c' at offset 4, got {magic_c}")
                return False
            
            # Skip 2 bytes (offset 6-7)
            f.read(2)
            
            # Version at offset 8 (Int16)
            self.version = struct.unpack('<H', f.read(2))[0]
            if self.version < 1 or self.version > 3:
                print(f"Error: Unsupported version {self.version}")
                return False
            
            # Entry count at offset 0xA (Int16)
            count = struct.unpack('<H', f.read(2))[0]
            if count <= 0 or count >= 0x40000:
                print(f"Error: Invalid entry count {count}")
                return False
            
            # Index offset at offset 0xC (UInt32)
            index_offset = struct.unpack('<I', f.read(4))[0]
            
            # Get file size
            f.seek(0, 2)  # Seek to end
            self._file_size = f.tell()
            
            if index_offset >= self._file_size:
                print(f"Error: Index offset {index_offset} exceeds file size {self._file_size}")
                return False
            
            # Try to read index
            f.seek(index_offset)
            
            entries = None
            if self.version > 1:
                entries = self._read_v2(f, count, index_offset)
            
            if entries is None:
                f.seek(index_offset)
                entries = self._read_v1(f, count, index_offset)
            
            if entries is None:
                print("Error: Failed to read index")
                return False
            
            self.entries = entries
            return True
    
    def _read_string(self, f, max_length: int) -> str:
        """Read a null-terminated string"""
        data = f.read(max_length)
        # Find null terminator
        null_pos = data.find(b'\x00')
        if null_pos >= 0:
            data = data[:null_pos]
        # Try multiple encodings
        for encoding in ['shift_jis', 'utf-8', 'cp932', 'latin-1']:
            try:
                return data.decode(encoding)
            except:
                continue
        return data.decode('latin-1', errors='replace')
    
    def _read_v1(self, f, count: int, index_offset: int) -> Optional[List[BsaEntry]]:
        """Read V1 format index"""
        entries = []
        path_stack = []
        
        f.seek(index_offset)
        
        for i in range(count):
            # Read name (0x20 bytes)
            name = self._read_string(f, 0x20)
            if len(name) == 0:
                return None
            
            # Seek back and forward to read offset and size
            current_pos = index_offset + i * 0x28
            f.seek(current_pos + 0x20)
            
            entry_offset = struct.unpack('<I', f.read(4))[0]
            entry_size = struct.unpack('<I', f.read(4))[0]
            
            if name.startswith('>'):
                # Enter directory
                path_stack.append(name[1:])
            elif name.startswith('<'):
                # Leave directory
                if path_stack:
                    path_stack.pop()
            else:
                # Regular file
                if path_stack:
                    full_name = os.path.join(*path_stack, name)
                else:
                    full_name = name
                
                # Validate placement
                if entry_offset + entry_size > self._file_size:
                    print(f"Warning: Entry '{full_name}' exceeds file boundary")
                    return None
                
                entries.append(BsaEntry(full_name, entry_offset, entry_size))
            
            # Move to next entry
            f.seek(current_pos + 0x28)
        
        return entries
    
    def _read_v2(self, f, count: int, index_offset: int) -> Optional[List[BsaEntry]]:
        """Read V2 format index"""
        entries = []
        path_stack = []
        
        # Names are stored after the index entries
        filenames_offset = index_offset + count * 12
        
        # Read all names into buffer
        f.seek(filenames_offset)
        names_buf = f.read()
        
        f.seek(index_offset)
        
        for i in range(count):
            current_pos = index_offset + i * 12
            f.seek(current_pos)
            
            # Read name offset (4 bytes)
            name_offset = struct.unpack('<I', f.read(4))[0]
            
            if name_offset >= len(names_buf):
                return None
            
            # Read null-terminated string from names buffer
            null_pos = names_buf.find(b'\x00', name_offset)
            if null_pos < 0:
                null_pos = len(names_buf)
            name_bytes = names_buf[name_offset:null_pos]
            
            # Decode name
            for encoding in ['shift_jis', 'utf-8', 'cp932', 'latin-1']:
                try:
                    name = name_bytes.decode(encoding)
                    break
                except:
                    continue
            else:
                name = name_bytes.decode('latin-1', errors='replace')
            
            if len(name) == 0:
                return None
            
            # Read offset and size
            entry_offset = struct.unpack('<I', f.read(4))[0]
            entry_size = struct.unpack('<I', f.read(4))[0]
            
            if name.startswith('>'):
                # Enter directory
                path_stack.append(name[1:])
            elif name.startswith('<'):
                # Leave directory
                if path_stack:
                    path_stack.pop()
            else:
                # Regular file
                if path_stack:
                    full_name = os.path.join(*path_stack, name)
                else:
                    full_name = name
                
                # Validate placement
                if entry_offset + entry_size > self._file_size:
                    print(f"Warning: Entry '{full_name}' exceeds file boundary")
                    return None
                
                entries.append(BsaEntry(full_name, entry_offset, entry_size))
        
        return entries
    
    def extract_all(self, output_dir: str, verbose: bool = True):
        """Extract all files to the specified directory"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        with open(self.filepath, 'rb') as f:
            for entry in self.entries:
                # Create output path
                entry_path = output_path / entry.name
                entry_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Read and write data
                f.seek(entry.offset)
                data = f.read(entry.size)
                
                with open(entry_path, 'wb') as out_f:
                    out_f.write(data)
                
                if verbose:
                    print(f"Extracted: {entry.name} ({entry.size} bytes)")
        
        if verbose:
            print(f"\nExtracted {len(self.entries)} files to {output_dir}")
    
    def list_contents(self):
        """List archive contents"""
        print(f"BSA Archive: {self.filepath}")
        print(f"Version: {self.version}")
        print(f"Entries: {len(self.entries)}")
        print("-" * 60)
        print(f"{'Offset':>10}  {'Size':>10}  Name")
        print("-" * 60)
        for entry in self.entries:
            print(f"{entry.offset:>10}  {entry.size:>10}  {entry.name}")


def extract_bsa_file(bsa_path: str, output_dir: str, verbose: bool = True) -> bool:
    """Extract a single BSA file"""
    archive = BsaArchive(bsa_path)
    if not archive.open():
        return False
    
    archive.extract_all(output_dir, verbose)
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Extract Bishop BSA archives (based on GARbro implementation)'
    )
    parser.add_argument(
        'input',
        nargs='?',
        help='BSA file or directory containing BSA files'
    )
    parser.add_argument(
        '-o', '--output',
        default='extracted',
        help='Output directory (default: extracted)'
    )
    parser.add_argument(
        '-l', '--list',
        action='store_true',
        help='List contents without extracting'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress output'
    )
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help='Extract all BSA files from BSA directory'
    )
    
    args = parser.parse_args()
    
    # Default to BSA directory if no input specified
    if args.input is None:
        if args.all:
            args.input = os.path.join(os.path.dirname(__file__), 'BSA')
        else:
            parser.print_help()
            return
    
    input_path = Path(args.input)
    
    if input_path.is_file():
        # Single file
        if args.list:
            archive = BsaArchive(str(input_path))
            if archive.open():
                archive.list_contents()
        else:
            # Create subdirectory based on BSA filename
            bsa_name = input_path.stem
            output_dir = os.path.join(args.output, bsa_name)
            extract_bsa_file(str(input_path), output_dir, not args.quiet)
    
    elif input_path.is_dir():
        # Directory - process all BSA files
        bsa_files = list(input_path.glob('*.bsa'))
        if not bsa_files:
            print(f"No BSA files found in {input_path}")
            return
        
        print(f"Found {len(bsa_files)} BSA file(s)")
        print("=" * 60)
        
        for bsa_file in sorted(bsa_files):
            print(f"\nProcessing: {bsa_file.name}")
            print("-" * 40)
            
            if args.list:
                archive = BsaArchive(str(bsa_file))
                if archive.open():
                    archive.list_contents()
            else:
                # Create subdirectory for each BSA
                bsa_name = bsa_file.stem
                output_dir = os.path.join(args.output, bsa_name)
                extract_bsa_file(str(bsa_file), output_dir, not args.quiet)
    
    else:
        print(f"Error: '{args.input}' not found")


if __name__ == '__main__':
    main()
