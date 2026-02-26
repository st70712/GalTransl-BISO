#!/usr/bin/env python3
"""
BSG (BSS-Graphics) Image Converter
Based on GARbro's ImageBSG.cs implementation by morkt
Converts Bishop engine BSG images to PNG format

Supports:
- BSS-Graphics format
- BSS-Composition format (with embedded graphics)
- Color modes: BGRA32, BGR32, Indexed8
- Compression modes: None, RLE, LZ

Author: Based on GARbro (https://github.com/morkt/GARbro)
License: MIT
"""

import os
import struct
import argparse
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL/Pillow not installed. Install with: pip install Pillow numpy")


@dataclass
class BsgMetaData:
    """BSG image metadata"""
    width: int
    height: int
    offset_x: int
    offset_y: int
    unpacked_size: int
    bpp: int  # bits per pixel
    color_mode: int  # 0=BGRA32, 1=BGR32, 2=Indexed8
    compression_mode: int  # 0=None, 1=RLE, 2=LZ
    data_offset: int
    data_size: int
    palette_offset: int
    base_offset: int  # for composition format


class BsgReader:
    """BSG image reader/decoder"""
    
    # Signature: 'BSS-' (0x2D535342)
    SIGNATURE = b'BSS-'
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.data = None
        self.meta: Optional[BsgMetaData] = None
        self.output: Optional[bytes] = None
        self.palette: Optional[List[Tuple[int, int, int, int]]] = None
        
    def read_metadata(self, data: bytes) -> Optional[BsgMetaData]:
        """Read BSG file metadata from header"""
        if len(data) < 0x60:
            return None
            
        # Check for BSS-Composition header (has embedded BSS-Graphics)
        base_offset = 0
        if data[:16] == b'BSS-Composition\x00':
            base_offset = 0x20
        
        # Check for BSS-Graphics signature
        if data[base_offset:base_offset+13] != b'BSS-Graphics\x00':
            return None
            
        # Read type/color mode
        color_mode = data[base_offset + 0x30]
        if color_mode > 2:
            return None
            
        # Parse header fields
        width = struct.unpack_from('<H', data, base_offset + 0x16)[0]
        height = struct.unpack_from('<H', data, base_offset + 0x18)[0]
        offset_x = struct.unpack_from('<h', data, base_offset + 0x20)[0]
        offset_y = struct.unpack_from('<h', data, base_offset + 0x22)[0]
        unpacked_size = struct.unpack_from('<I', data, base_offset + 0x12)[0]
        compression_mode = data[base_offset + 0x31]
        data_offset = struct.unpack_from('<I', data, base_offset + 0x32)[0] + base_offset
        data_size = struct.unpack_from('<I', data, base_offset + 0x36)[0]
        palette_offset = struct.unpack_from('<I', data, base_offset + 0x3A)[0] + base_offset
        
        # Determine BPP
        bpp = 8 if color_mode == 2 else 32
        
        return BsgMetaData(
            width=width,
            height=height,
            offset_x=offset_x,
            offset_y=offset_y,
            unpacked_size=unpacked_size,
            bpp=bpp,
            color_mode=color_mode,
            compression_mode=compression_mode,
            data_offset=data_offset,
            data_size=data_size,
            palette_offset=palette_offset,
            base_offset=base_offset
        )
    
    def read_palette(self, data: bytes, offset: int) -> List[Tuple[int, int, int, int]]:
        """Read 256-color palette (RGBA format)"""
        palette = []
        for i in range(256):
            if offset + i * 4 + 4 <= len(data):
                b, g, r, a = struct.unpack_from('BBBB', data, offset + i * 4)
                palette.append((r, g, b, 255))  # Convert to RGBA, ignore alpha
            else:
                palette.append((0, 0, 0, 255))
        return palette
    
    def unpack_none(self, data: bytes, meta: BsgMetaData) -> bytes:
        """Unpack uncompressed data"""
        output = bytearray(meta.unpacked_size)
        src_offset = meta.data_offset
        
        if meta.color_mode == 1:  # BGR32 - need to expand 3 bytes to 4
            dst = 0
            count = meta.data_size // 3
            for _ in range(count):
                if src_offset + 3 <= len(data):
                    output[dst:dst+3] = data[src_offset:src_offset+3]
                    dst += 4
                    src_offset += 3
        else:
            # Direct copy for BGRA32 or Indexed8
            end = min(src_offset + meta.data_size, len(data))
            copy_size = min(end - src_offset, meta.unpacked_size)
            output[:copy_size] = data[src_offset:src_offset + copy_size]
        
        return bytes(output)
    
    def unpack_rle(self, data: bytes, meta: BsgMetaData) -> bytes:
        """Unpack RLE compressed data"""
        output = bytearray(meta.unpacked_size)
        
        # Determine pixel size and channels
        if meta.color_mode == 2:  # Indexed8
            pixel_size = 1
            channels = 1
        else:  # BGRA32 or BGR32
            pixel_size = 4
            channels = 4 if meta.color_mode == 0 else 3
        
        src_pos = meta.data_offset
        
        for channel in range(channels):
            dst = channel
            
            if src_pos + 4 > len(data):
                break
                
            remaining = struct.unpack_from('<I', data, src_pos)[0]
            src_pos += 4
            
            while remaining > 0 and dst < len(output):
                if src_pos >= len(data):
                    break
                    
                count = struct.unpack_from('b', data, src_pos)[0]  # signed byte
                src_pos += 1
                remaining -= 1
                
                if count >= 0:
                    # Literal run
                    for _ in range(count + 1):
                        if src_pos >= len(data) or dst >= len(output):
                            break
                        output[dst] = data[src_pos]
                        src_pos += 1
                        remaining -= 1
                        dst += pixel_size
                else:
                    # Repeat run
                    repeat_count = 1 - count
                    if src_pos >= len(data):
                        break
                    repeat_byte = data[src_pos]
                    src_pos += 1
                    remaining -= 1
                    
                    for _ in range(repeat_count):
                        if dst >= len(output):
                            break
                        output[dst] = repeat_byte
                        dst += pixel_size
        
        return bytes(output)
    
    def unpack_lz(self, data: bytes, meta: BsgMetaData) -> bytes:
        """Unpack LZ compressed data"""
        output = bytearray(meta.unpacked_size)
        
        # Determine pixel size and channels
        if meta.color_mode == 2:  # Indexed8
            pixel_size = 1
            channels = 1
        else:  # BGRA32 or BGR32
            pixel_size = 4
            channels = 4 if meta.color_mode == 0 else 3
        
        src_pos = meta.data_offset
        
        for channel in range(channels):
            dst = channel
            
            if src_pos >= len(data):
                break
            
            control = data[src_pos]
            src_pos += 1
            
            if src_pos + 4 > len(data):
                break
            
            remaining = struct.unpack_from('<I', data, src_pos)[0] - 5
            src_pos += 4
            
            while remaining > 0 and dst < len(output):
                if src_pos >= len(data):
                    break
                
                c = data[src_pos]
                src_pos += 1
                remaining -= 1
                
                if c == control:
                    if src_pos >= len(data):
                        break
                    
                    offset = data[src_pos]
                    src_pos += 1
                    remaining -= 1
                    
                    if offset != control:
                        if src_pos >= len(data):
                            break
                        
                        count = data[src_pos]
                        src_pos += 1
                        remaining -= 1
                        
                        if offset > control:
                            offset -= 1
                        
                        offset *= pixel_size
                        
                        for _ in range(count):
                            if dst >= len(output):
                                break
                            if dst >= offset:
                                output[dst] = output[dst - offset]
                            dst += pixel_size
                        continue
                    else:
                        # Escape sequence - output control byte
                        c = control
                
                if dst < len(output):
                    output[dst] = c
                    dst += pixel_size
            
            # Apply delta filter
            for i in range(channel + pixel_size, len(output), pixel_size):
                output[i] = (output[i] + output[i - pixel_size]) & 0xFF
        
        return bytes(output)
    
    def unpack(self) -> bool:
        """Read and unpack the BSG image"""
        try:
            with open(self.filepath, 'rb') as f:
                self.data = f.read()
        except IOError as e:
            print(f"Error reading file: {e}")
            return False
        
        # Parse metadata
        self.meta = self.read_metadata(self.data)
        if self.meta is None:
            print(f"Error: Not a valid BSG file or unsupported format")
            return False
        
        # Validate compression mode
        if self.meta.compression_mode > 2:
            print(f"Error: Unsupported compression mode {self.meta.compression_mode}")
            return False
        
        # Read palette for indexed mode
        if self.meta.color_mode == 2:
            self.palette = self.read_palette(self.data, self.meta.palette_offset)
        
        # Decompress data
        if self.meta.compression_mode == 0:
            self.output = self.unpack_none(self.data, self.meta)
        elif self.meta.compression_mode == 1:
            self.output = self.unpack_rle(self.data, self.meta)
        elif self.meta.compression_mode == 2:
            self.output = self.unpack_lz(self.data, self.meta)
        
        return True
    
    def to_image(self) -> Optional['Image.Image']:
        """Convert unpacked data to PIL Image"""
        if not HAS_PIL:
            print("Error: PIL/Pillow is required for image conversion")
            return None
        
        if self.output is None or self.meta is None:
            return None
        
        width = self.meta.width
        height = self.meta.height
        
        if self.meta.color_mode == 2:  # Indexed8
            # Create indexed image
            img = Image.frombytes('P', (width, height), self.output)
            
            # Apply palette
            if self.palette:
                flat_palette = []
                for r, g, b, a in self.palette:
                    flat_palette.extend([r, g, b])
                img.putpalette(flat_palette)
            
            # Convert to RGBA
            img = img.convert('RGBA')
        else:
            # BGRA32 or BGR32
            expected_size = width * height * 4
            if len(self.output) < expected_size:
                # Pad with zeros if needed
                self.output = self.output + bytes(expected_size - len(self.output))
            
            # Create numpy array and convert BGRA to RGBA
            arr = np.frombuffer(self.output[:expected_size], dtype=np.uint8)
            arr = arr.reshape((height, width, 4))
            
            # Swap B and R channels (BGRA -> RGBA)
            arr = arr[:, :, [2, 1, 0, 3]]
            
            # Flip vertically (BSG stores bottom-up)
            arr = np.flipud(arr)
            
            if self.meta.color_mode == 1:  # BGR32 - set alpha to 255
                arr[:, :, 3] = 255
            
            img = Image.fromarray(arr, 'RGBA')
        
        return img
    
    def save_png(self, output_path: str) -> bool:
        """Save as PNG image"""
        img = self.to_image()
        if img is None:
            return False
        
        try:
            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            img.save(output_path, 'PNG')
            return True
        except IOError as e:
            print(f"Error saving image: {e}")
            return False
    
    def get_info(self) -> str:
        """Get image info string"""
        if self.meta is None:
            return "No metadata available"
        
        color_modes = {0: "BGRA32", 1: "BGR32", 2: "Indexed8"}
        compression_modes = {0: "None", 1: "RLE", 2: "LZ"}
        
        return (
            f"Size: {self.meta.width}x{self.meta.height}\n"
            f"Offset: ({self.meta.offset_x}, {self.meta.offset_y})\n"
            f"Color Mode: {color_modes.get(self.meta.color_mode, 'Unknown')}\n"
            f"Compression: {compression_modes.get(self.meta.compression_mode, 'Unknown')}\n"
            f"BPP: {self.meta.bpp}\n"
            f"Data Size: {self.meta.data_size} bytes\n"
            f"Unpacked Size: {self.meta.unpacked_size} bytes"
        )


def convert_file(input_path: str, output_path: str, verbose: bool = True) -> bool:
    """Convert a single BSG file to PNG"""
    reader = BsgReader(input_path)
    
    if not reader.unpack():
        return False
    
    if verbose:
        print(f"Converting: {input_path}")
        print(f"  {reader.meta.width}x{reader.meta.height}, ", end='')
        color_modes = {0: "BGRA32", 1: "BGR32", 2: "Indexed8"}
        compression_modes = {0: "None", 1: "RLE", 2: "LZ"}
        print(f"{color_modes.get(reader.meta.color_mode, '?')}, ", end='')
        print(f"{compression_modes.get(reader.meta.compression_mode, '?')} compression")
    
    if reader.save_png(output_path):
        if verbose:
            print(f"  -> {output_path}")
        return True
    
    return False


def convert_directory(input_dir: str, output_dir: str, verbose: bool = True) -> Tuple[int, int]:
    """Convert all BSG files in a directory"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    bsg_files = list(input_path.rglob('*.bsg'))
    
    if not bsg_files:
        print(f"No BSG files found in {input_dir}")
        return 0, 0
    
    success = 0
    failed = 0
    
    for bsg_file in bsg_files:
        # Preserve directory structure
        relative = bsg_file.relative_to(input_path)
        out_file = output_path / relative.with_suffix('.png')
        
        if convert_file(str(bsg_file), str(out_file), verbose):
            success += 1
        else:
            failed += 1
            if verbose:
                print(f"  Failed: {bsg_file}")
    
    return success, failed


def main():
    parser = argparse.ArgumentParser(
        description='Convert Bishop BSG images to PNG format (based on GARbro)'
    )
    parser.add_argument(
        'input',
        help='Input BSG file or directory'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file or directory (default: same as input with .png extension)'
    )
    parser.add_argument(
        '-i', '--info',
        action='store_true',
        help='Show image info without converting'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress output'
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Process directories recursively'
    )
    
    args = parser.parse_args()
    
    if not HAS_PIL and not args.info:
        print("Error: PIL/Pillow and numpy are required for image conversion")
        print("Install with: pip install Pillow numpy")
        return 1
    
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"Error: '{args.input}' not found")
        return 1
    
    if input_path.is_file():
        if args.info:
            reader = BsgReader(str(input_path))
            if reader.unpack():
                print(f"File: {input_path}")
                print(reader.get_info())
            else:
                print(f"Error: Could not read {input_path}")
                return 1
        else:
            output = args.output or str(input_path.with_suffix('.png'))
            if not convert_file(str(input_path), output, not args.quiet):
                return 1
    
    elif input_path.is_dir():
        output_dir = args.output or str(input_path) + '_png'
        
        if args.info:
            # Just show info for all BSG files
            for bsg_file in input_path.rglob('*.bsg') if args.recursive else input_path.glob('*.bsg'):
                reader = BsgReader(str(bsg_file))
                if reader.unpack():
                    print(f"\n{bsg_file}:")
                    print(reader.get_info())
        else:
            success, failed = convert_directory(
                str(input_path), 
                output_dir, 
                not args.quiet
            )
            
            if not args.quiet:
                print(f"\nConversion complete: {success} succeeded, {failed} failed")
    
    return 0


if __name__ == '__main__':
    exit(main())
