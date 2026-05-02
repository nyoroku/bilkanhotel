import re

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\table_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_styles = """<style>
    /* Table Detail — uses design system tokens */
    .table-container{max-width:1400px;margin:0 auto;padding:1rem 0}
    
    .table-header{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem 2rem;margin-bottom:1.5rem;display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;box-shadow:var(--s1)}
    .table-title{font-size:1.5rem;font-weight:700;color:var(--txt1);margin:0;display:flex;align-items:center;gap:.75rem}
    .table-badge{display:inline-flex;align-items:center;gap:.5rem;background:var(--primary);color:#fff;padding:.5rem 1rem;border-radius:8px;font-weight:700;font-size:.9rem}
    
    .main-grid{display:grid;grid-template-columns:1fr 320px;gap:1.5rem;align-items:start}
    
    .orders-section{background:var(--surface);border:1px solid var(--border);border-radius:12px;box-shadow:var(--s1);overflow:hidden}
    .section-header{padding:1.25rem 1.5rem;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
    .section-title{font-size:1.1rem;font-weight:700;color:var(--txt1);margin:0;display:flex;align-items:center;gap:.5rem}
    
    .add-order-btn{background:var(--primary);color:#fff;padding:.6rem 1rem;border-radius:8px;font-weight:600;display:inline-flex;align-items:center;gap:.5rem;transition:transform .15s}
    .add-order-btn:hover{transform:translateY(-1px);color:#fff}
    
    .orders-list{padding:1.5rem}
    .order-card{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:1rem;margin-bottom:1rem;transition:border-color .15s}
    .order-card:hover{border-color:var(--primary)}
    .order-card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem;padding-bottom:.75rem;border-bottom:1px dashed var(--border)}
    
    .order-item{display:flex;justify-content:space-between;padding:.4rem 0;font-size:.85rem;color:var(--txt1)}
    .order-item-qty{color:var(--txt2);font-weight:600;margin-right:.5rem}
    
    .actions-panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem;box-shadow:var(--s1)}
    .panel-title{font-size:1.1rem;font-weight:700;color:var(--txt1);margin-bottom:1.25rem;display:flex;align-items:center;gap:.5rem}
    
    .action-button{display:flex;align-items:center;gap:.75rem;width:100%;padding:1rem;border-radius:10px;font-weight:600;font-size:.9rem;border:1px solid var(--border);background:var(--bg);color:var(--txt1);margin-bottom:.75rem;transition:all .15s;cursor:pointer}
    .action-button:hover{border-color:var(--primary);transform:translateY(-1px);box-shadow:var(--s1)}
    .action-button.primary{background:var(--primary);color:#fff;border-color:var(--primary)}
    .action-button.danger{background:rgba(239,68,68,.1);color:var(--error);border-color:rgba(239,68,68,.2)}
    
    @media(max-width:768px){
        .main-grid{grid-template-columns:1fr}
        .table-header{padding:1.25rem}
    }
</style>"""

new_content = re.sub(r'<style>.*?</style>', new_styles, content, flags=re.DOTALL)
new_content = new_content.replace('class="modern-container"', 'class="table-container"')
new_content = new_content.replace('class="page-header"', 'class="table-header"')
new_content = new_content.replace('class="page-title"', 'class="table-title"')
new_content = new_content.replace('class="back-btn"', 'class="btn btn-secondary"')

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\table_detail.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Replaced styles successfully.")
