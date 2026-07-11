with open("templates/index.html", "r", encoding="utf-8") as f:
    local_html = f.read()

print("--- LOCAL FILE CHECK ---")
print(f"Index of 'panel-history' in file: {local_html.find('panel-history')}")
print(f"Index of 'modal-overlay' in file: {local_html.find('modal-overlay')}")
print(f"Index of '</main>' in file: {local_html.find('</main>')}")

# Let's search for </main> case-insensitive
print(f"Index of '</main>' (lower) in file: {local_html.lower().find('</main>')}")
print(f"Index of '</main>' (lower) in fetched: {local_html.lower().find('</main>')}")

# Let's print lines 115-130 from the file
lines = local_html.splitlines()
print("\n--- LINES 115-135 IN FILE ---")
for i in range(114, min(len(lines), 135)):
    print(f"{i+1}: {lines[i]}")
