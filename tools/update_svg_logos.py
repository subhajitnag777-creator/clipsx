import base64

def b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

# logo.svg
with open('web/brand/logo.svg', 'w', encoding='utf-8') as f:
    f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2169 718" width="2169" height="718"><image href="data:image/png;base64,{b64("web/brand/clipsx-full.png")}" width="2169" height="718"/></svg>\n')

# logo-light.svg
with open('web/brand/logo-light.svg', 'w', encoding='utf-8') as f:
    f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2169 718" width="2169" height="718"><image href="data:image/png;base64,{b64("web/brand/clipsx-full-light.png")}" width="2169" height="718"/></svg>\n')

# favicon.svg
with open('web/brand/favicon.svg', 'w', encoding='utf-8') as f:
    f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 718 718" width="718" height="718"><image href="data:image/png;base64,{b64("web/brand/clipsx-icon.png")}" width="718" height="718"/></svg>\n')

print('SVGs successfully generated with embedded high-res assets.')
