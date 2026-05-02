import re

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\admin_dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the "Sales This Week" chart wrapper
pattern_chart = r'<div class="flex flex-wrap -mx-3 mt-4">\s*<div class="w-full px-3 md:w-2/3">\s*<div class="bg-white rounded-lg shadow-md overflow-hidden">'
replacement_chart = r'<div class="mod-grid" style="margin-top:2rem">\n    <div class="w-full">\n        <div class="tbl-card">'
content = re.sub(pattern_chart, replacement_chart, content, count=1, flags=re.DOTALL)

# Replace the header for Sales This Week
pattern_header = r'<header class="border-b border-gray-200 px-6 py-4 flex items-center justify-between">\s*<p class="text-lg font-bold text-gray-800">Sales This Week</p>\s*</header>'
replacement_header = r'<div style="padding:1.5rem;border-bottom:1px solid var(--border);font-weight:700;font-size:1.1rem;color:var(--txt1)">Sales This Week</div>'
content = re.sub(pattern_header, replacement_header, content, count=1, flags=re.DOTALL)

# Replace the Draft Purchase Orders card wrapper
pattern_po = r'<div class="bg-white rounded-lg shadow-md overflow-hidden mt-4" id="purchaseOrdersCard">'
replacement_po = r'<div class="tbl-card" style="margin-top:2rem" id="purchaseOrdersCard">'
content = re.sub(pattern_po, replacement_po, content, count=1, flags=re.DOTALL)

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\admin_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated admin dashboard charts wrapper.")
