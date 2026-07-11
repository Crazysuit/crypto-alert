"""Generate PNG icons from SVG for PWA using cairosvg or Pillow fallback."""
import os
import sys

ICON_DIR = os.path.join(os.path.dirname(__file__), 'static', 'icons')
SVG_PATH = os.path.join(ICON_DIR, 'icon.svg')

def generate_with_cairosvg():
    import cairosvg
    for size in [192, 512]:
        out = os.path.join(ICON_DIR, f'icon-{size}.png')
        cairosvg.svg2png(url=SVG_PATH, write_to=out, output_width=size, output_height=size)
        print(f'Generated {out} ({size}x{size})')

def generate_with_pillow():
    """Create simple gradient icons with Pillow if cairosvg not available."""
    from PIL import Image, ImageDraw
    
    for size in [192, 512]:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Background rounded rect
        margin = int(size * 0.05)
        radius = int(size * 0.21)
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=radius,
            fill=(10, 10, 26, 255)
        )
        
        # Outer ring
        cx, cy = size // 2, size // 2
        r = int(size * 0.35)
        ring_w = max(2, int(size * 0.015))
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=(0, 212, 255, 150),
            width=ring_w
        )
        
        # Chart line points (scaled)
        def s(x, y):
            return (int(x / 512 * size), int(y / 512 * size))
        
        points = [s(160, 310), s(220, 220), s(256, 270), s(310, 170), s(350, 210)]
        line_w = max(3, int(size * 0.027))
        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=(0, 212, 255, 230), width=line_w)
        
        # Alert dot
        dot_r = int(size * 0.035)
        dx, dy = s(350, 210)
        draw.ellipse(
            [dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r],
            fill=(0, 255, 136, 230)
        )
        inner_r = int(dot_r * 0.55)
        draw.ellipse(
            [dx - inner_r, dy - inner_r, dx + inner_r, dy + inner_r],
            fill=(255, 255, 255, 255)
        )
        
        # Start dot
        sx, sy = s(160, 310)
        sr = int(size * 0.015)
        draw.ellipse(
            [sx - sr, sy - sr, sx + sr, sy + sr],
            fill=(0, 212, 255, 180)
        )
        
        out = os.path.join(ICON_DIR, f'icon-{size}.png')
        img.save(out, 'PNG')
        print(f'Generated {out} ({size}x{size})')

def generate_minimal():
    """Absolute fallback: create a simple colored square PNG manually."""
    import struct, zlib
    
    for size in [192, 512]:
        # Create a simple dark blue square with a cyan accent
        pixels = []
        cx, cy = size // 2, size // 2
        for y in range(size):
            row = []
            for x in range(size):
                # Distance from center
                dx = abs(x - cx)
                dy = abs(y - cy)
                # Rounded rect check
                rect_half = int(size * 0.45)
                radius = int(size * 0.2)
                
                in_rect = dx <= rect_half and dy <= rect_half
                if dx > rect_half - radius and dy > rect_half - radius:
                    corner_dist = ((dx - (rect_half - radius))**2 + (dy - (rect_half - radius))**2) ** 0.5
                    in_rect = corner_dist <= radius
                
                if not in_rect:
                    row.extend([0, 0, 0, 0])  # transparent
                else:
                    # Background gradient
                    t = (x + y) / (2 * size)
                    r = int(10 + t * 10)
                    g = int(10 + t * 8)
                    b = int(26 + t * 12)
                    
                    # Draw a simple lightning bolt shape
                    # Check if near the chart line
                    chart_points = [
                        (0.3125, 0.605),  # 160/512, 310/512
                        (0.4297, 0.4297),  # 220/512
                        (0.5, 0.5273),      # 256/512, 270/512
                        (0.6055, 0.332),    # 310/512, 170/512
                        (0.6836, 0.4102),   # 350/512, 210/512
                    ]
                    nx, ny = x / size, y / size
                    near_line = False
                    threshold = 0.025
                    for i in range(len(chart_points) - 1):
                        x1, y1 = chart_points[i]
                        x2, y2 = chart_points[i + 1]
                        # Point-to-line-segment distance
                        dx_l = x2 - x1
                        dy_l = y2 - y1
                        if dx_l == 0 and dy_l == 0:
                            d = ((nx - x1)**2 + (ny - y1)**2) ** 0.5
                        else:
                            t_param = max(0, min(1, ((nx - x1) * dx_l + (ny - y1) * dy_l) / (dx_l**2 + dy_l**2)))
                            proj_x = x1 + t_param * dx_l
                            proj_y = y1 + t_param * dy_l
                            d = ((nx - proj_x)**2 + (ny - proj_y)**2) ** 0.5
                        if d < threshold:
                            near_line = True
                            break
                    
                    if near_line:
                        # Cyan-green gradient line
                        r, g, b = 0, 212, 255
                    
                    # Alert dot at top right of chart
                    dot_cx, dot_cy = 0.6836, 0.4102
                    dot_dist = ((nx - dot_cx)**2 + (ny - dot_cy)**2) ** 0.5
                    if dot_dist < 0.04:
                        r, g, b = 0, 255, 136
                    if dot_dist < 0.022:
                        r, g, b = 255, 255, 255
                    
                    row.extend([r, g, b, 255])
            pixels.append(bytes(row))
        
        # Build PNG manually
        def make_png(width, height, rows):
            def chunk(chunk_type, data):
                c = chunk_type + data
                crc = struct.pack('>I', zlib.crc32(c) & 0xffffffff)
                return struct.pack('>I', len(data)) + c + crc
            
            header = b'\x89PNG\r\n\x1a\n'
            ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            
            raw = b''
            for row in rows:
                raw += b'\x00' + row  # filter byte 0 (None)
            
            compressed = zlib.compress(raw, 9)
            idat = chunk(b'IDAT', compressed)
            iend = chunk(b'IEND', b'')
            
            return header + ihdr + idat + iend
        
        png_data = make_png(size, size, pixels)
        out = os.path.join(ICON_DIR, f'icon-{size}.png')
        with open(out, 'wb') as f:
            f.write(png_data)
        print(f'Generated {out} ({size}x{size})')

if __name__ == '__main__':
    try:
        generate_with_cairosvg()
    except ImportError:
        print('cairosvg not available, trying Pillow...')
        try:
            generate_with_pillow()
        except ImportError:
            print('Pillow not available, using minimal PNG generator...')
            generate_minimal()
    print('Done!')
