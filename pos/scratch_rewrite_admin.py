import re

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\admin_dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the header
header_pattern = r'<div class="mb-6">.*?</div>'
new_header = """<div class="page-hdr">
    <div>
        <h1><i class="fas fa-chart-line text-primary"></i> Admin Dashboard</h1>
        <p class="page-hdr-sub">Welcome Back, {{ request.user.first_name|default:request.user.email }}! Here's a snapshot of today's performance.</p>
    </div>
</div>"""
content = re.sub(header_pattern, new_header, content, count=1, flags=re.DOTALL)

# Replace KPI grid
kpi_pattern = r'<div class="flex flex-wrap -mx-3 is-multiline">.*?</div>\s*</div>\s*</div>\s*</div>\s*</div>'
new_kpi = """<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-ico kpi-ico--success"><i class="fas fa-coins"></i></div>
        <div class="kpi-lbl">Total Sales Today</div>
        <div class="kpi-val">{{ kpi_data.total_sales|floatformat:2 }} <span style="font-size:1rem;color:var(--txt2)">KES</span></div>
    </div>
    <div class="kpi-card">
        <div class="kpi-ico kpi-ico--info"><i class="fas fa-receipt"></i></div>
        <div class="kpi-lbl">Orders Today</div>
        <div class="kpi-val">{{ kpi_data.total_orders }}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-ico kpi-ico--warning"><i class="fas fa-chart-pie"></i></div>
        <div class="kpi-lbl">Average Sale</div>
        <div class="kpi-val">{{ kpi_data.average_sale|floatformat:2 }} <span style="font-size:1rem;color:var(--txt2)">KES</span></div>
    </div>
    <div class="kpi-card">
        <div class="kpi-ico kpi-ico--error"><i class="fas fa-star"></i></div>
        <div class="kpi-lbl">Top Seller</div>
        <div class="kpi-val" style="font-size:1.2rem">{{ kpi_data.top_selling_item }}</div>
    </div>
</div>"""
content = re.sub(kpi_pattern, new_kpi, content, count=1, flags=re.DOTALL)

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\admin_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated HTML structure in admin dashboard.")
