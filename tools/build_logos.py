import os
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

font_path = 'studio/fonts/Poppins-ExtraBold.ttf'
font = TTFont(font_path)
cmap = font.getBestCmap()
glyph_set = font.getGlyphSet()
hmtx = font['hmtx']

# Dimensions matching original
canvas_w = 796
canvas_h = 220
scale = 124.0 / 1000.0
baseline_y = 154.0
start_x = 277.0

# 1. Vector SVG Paths for 'Clips' and 'X'
curr_x = start_x
clips_paths = []
x_path = ''

chars = 'Clips X'
for i, ch in enumerate(chars):
    if ch == ' ':
        curr_x += hmtx['space'][0] * scale
        continue
    gname = cmap[ord(ch)]
    adv = hmtx[gname][0] * scale
    
    t_pen = SVGPathPen(glyph_set)
    tp = TransformPen(t_pen, (scale, 0, 0, -scale, curr_x, baseline_y))
    glyph_set[gname].draw(tp)
    
    cmd = t_pen.getCommands()
    if ch == 'X':
        x_path = cmd
    else:
        clips_paths.append(cmd)
    
    curr_x += adv

# Read the first 9 paths (mascot icon) from original SVG
with open('web/brand/logo.svg', 'r', encoding='utf-8') as f:
    orig_lines = f.readlines()
icon_lines = orig_lines[1:10]  # lines 2..10 (the 9 mascot paths)

# Generate logo.svg (Dark text on light background)
svg_dark_text = f'''<svg width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}" fill="none" xmlns="http://www.w3.org/2000/svg">\n'''
for l in icon_lines:
    svg_dark_text += l
for p in clips_paths:
    svg_dark_text += f'<path d="{p}" fill="#310001"/>\n'
svg_dark_text += f'<path d="{x_path}" fill="#FF8B33"/>\n</svg>\n'

with open('web/brand/logo.svg', 'w', encoding='utf-8') as f:
    f.write(svg_dark_text)

# Generate logo-light.svg (White text on dark background)
svg_light_text = f'''<svg width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}" fill="none" xmlns="http://www.w3.org/2000/svg">\n'''
for l in icon_lines:
    svg_light_text += l
for p in clips_paths:
    svg_light_text += f'<path d="{p}" fill="#FBF7F8"/>\n'
svg_light_text += f'<path d="{x_path}" fill="#FF8B33"/>\n</svg>\n'

with open('web/brand/logo-light.svg', 'w', encoding='utf-8') as f:
    f.write(svg_light_text)

print('SVGs written successfully.')

# 2. Render logo-email.png (796x220, RGBA, matching original mascot + crisp Clips X)
orig_png = Image.open('web/brand/logo-email.png')
icon_crop = orig_png.crop((0, 0, 225, 220))

# We render the text at 4x resolution for studio-quality antialiasing, then downscale
scale_factor = 4
large_w = canvas_w * scale_factor
large_h = canvas_h * scale_factor

large_img = Image.new('RGBA', (large_w, large_h), (0, 0, 0, 0))
large_draw = ImageDraw.Draw(large_img)
large_font = ImageFont.truetype(font_path, int(124 * scale_factor))

c_bbox = large_font.getbbox('C')
y_top_c = int(65 * scale_factor)
y_offset = y_top_c - c_bbox[1]
x_start = int(start_x * scale_factor)

# Draw 'Clips'
large_draw.text((x_start, y_offset), 'Clips', font=large_font, fill=(49, 0, 1, 255))
clips_len = large_draw.textlength('Clips ', font=large_font)
x_x_pos = int(x_start + clips_len)
# Draw 'X'
large_draw.text((x_x_pos, y_offset), 'X', font=large_font, fill=(255, 139, 51, 255))

# Downsample text layer with high quality LANCZOS filter
text_layer = large_img.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)

# Composite final image
final_png = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
final_png.paste(icon_crop, (0, 0))
final_png.alpha_composite(text_layer)

final_png.save('web/brand/logo-email.png', 'PNG')
print('web/brand/logo-email.png generated successfully.')

# Copy to artifacts directory
artifact_dir = r'C:\Users\subha\.gemini\antigravity\brain\2513bb19-73b1-4835-a7b7-1b6a596ffbb9'
artifact_png = os.path.join(artifact_dir, 'clipsx-logo.png')
final_png.save(artifact_png, 'PNG')
print('Artifact logo saved to:', artifact_png)
