import urllib.request

try:
    url = "http://localhost:5000/"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
    
    print("--- FETCH SUCCESSFUL ---")
    # Find position of panel-history
    idx_history = html.find('panel-history')
    idx_overlay = html.find('modal-overlay')
    idx_main_close = html.find('</main>')
    
    print(f"Index of 'panel-history': {idx_history}")
    print(f"Index of 'modal-overlay': {idx_overlay}")
    print(f"Index of '</main>': {idx_main_close}")
    
    # Check if modal-overlay is inside main or history panel
    # We can inspect the substring around modal-overlay
    start = max(0, idx_overlay - 200)
    end = min(len(html), idx_overlay + 200)
    print("\n--- HTML AROUND MODAL OVERLAY ---")
    print(html[start:end])
    
except Exception as e:
    print(f"Error: {e}")
