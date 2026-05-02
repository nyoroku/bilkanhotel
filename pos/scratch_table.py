import re

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\table_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_css = """<style>
    :root {
        --primary-vibrant: #4f46e5;
        --primary-vibrant-glow: 0 4px 15px rgba(79, 70, 229, 0.4);
        --success-vibrant: #10b981;
        --success-vibrant-glow: 0 4px 15px rgba(16, 185, 129, 0.4);
        --warning-vibrant: #f59e0b;
        --danger-vibrant: #ef4444;
        
        --card-shadow-soft: 0 10px 30px -5px rgba(0, 0, 0, 0.08);
        --card-hover-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.12);
        
        --border-radius: 0.75rem;
        --border-radius-lg: 1.25rem;
        --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    [data-theme="dark"] {
        --card-shadow-soft: 0 10px 30px -5px rgba(0, 0, 0, 0.4);
        --card-hover-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.6);
    }

    * { box-sizing: border-box; }

    .modern-container {
        max-width: 1400px;
        margin: 0 auto;
        padding: 2rem 1.5rem;
    }

    .page-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 2.5rem;
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
        padding: 2rem 2.5rem;
        border-radius: 20px;
        box-shadow: 0 20px 40px -10px rgba(49, 46, 129, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative;
        overflow: hidden;
    }

    .page-header::before {
        content: ''; position: absolute; top: 0; right: 0; bottom: 0; width: 50%;
        background: radial-gradient(circle at top right, rgba(99,102,241,0.3) 0%, transparent 70%);
        pointer-events: none;
    }

    .page-title {
        font-size: 2rem;
        font-weight: 800;
        color: white;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 1rem;
        position: relative;
        z-index: 1;
    }

    .table-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: var(--primary-vibrant);
        color: white;
        padding: 0.75rem 1.25rem;
        border-radius: var(--border-radius);
        font-weight: 800;
        font-size: 1.1rem;
        box-shadow: var(--primary-vibrant-glow);
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .back-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: rgba(255, 255, 255, 0.1);
        color: white;
        padding: 0.875rem 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: var(--border-radius);
        text-decoration: none;
        font-weight: 600;
        transition: var(--transition);
        position: relative;
        z-index: 1;
    }

    .back-btn:hover {
        background: rgba(255, 255, 255, 0.2);
        transform: translateY(-2px);
    }

    .main-grid {
        display: grid;
        grid-template-columns: 1fr 380px;
        gap: 2rem;
        align-items: start;
    }

    .orders-section {
        background: var(--surface);
        border-radius: var(--border-radius-lg);
        box-shadow: var(--card-shadow-soft);
        border: 1px solid var(--border);
        overflow: hidden;
    }

    .section-header {
        background: var(--bg);
        padding: 2rem;
        border-bottom: 1px solid var(--border);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .section-title {
        font-size: 1.5rem;
        font-weight: 800;
        color: var(--txt1);
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }

    .section-title::before {
        content: '';
        width: 6px;
        height: 24px;
        background: var(--primary-vibrant);
        border-radius: 3px;
    }

    .add-order-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: linear-gradient(135deg, var(--primary-vibrant) 0%, #3730a3 100%);
        color: white;
        padding: 0.875rem 1.5rem;
        border: none;
        border-radius: var(--border-radius);
        text-decoration: none;
        font-weight: 700;
        transition: var(--transition);
        box-shadow: var(--primary-vibrant-glow);
    }

    .add-order-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(79, 70, 229, 0.6);
    }

    .empty-state {
        padding: 5rem 2rem;
        text-align: center;
    }

    .empty-state-icon {
        width: 80px;
        height: 80px;
        background: var(--bg);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.5rem;
        color: var(--txt2);
        margin: 0 auto 1.5rem;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid var(--border);
    }

    .empty-state-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: var(--txt1);
        margin-bottom: 0.5rem;
    }

    .empty-state-text {
        color: var(--txt2);
        max-width: 400px;
        margin: 0 auto;
        line-height: 1.5;
    }

    .order-cards {
        padding: 1.5rem;
        display: grid;
        gap: 1.5rem;
    }

    .order-card {
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: var(--border-radius);
        padding: 1.5rem;
        transition: var(--transition);
        position: relative;
        overflow: hidden;
    }

    .order-card:hover {
        transform: translateY(-3px);
        box-shadow: var(--card-hover-shadow);
        border-color: var(--primary-vibrant);
    }

    .order-card::before {
        content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
        background: var(--primary-vibrant);
    }

    .order-card.status-pending::before { background: var(--warning-vibrant); }
    .order-card.status-in_progress::before { background: var(--info-vibrant); }
    .order-card.status-completed::before { background: var(--success-vibrant); }

    .order-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid var(--border);
    }

    .order-id {
        font-size: 1.125rem;
        font-weight: 800;
        color: var(--txt1);
        margin-bottom: 0.25rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .order-time {
        font-size: 0.875rem;
        color: var(--txt2);
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-weight: 500;
    }

    .status-badge {
        padding: 0.4rem 0.8rem;
        border-radius: 50px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .status-pending { background: rgba(245, 158, 11, 0.15); color: #d97706; }
    [data-theme="dark"] .status-pending { color: #fcd34d; }
    
    .status-in_progress { background: rgba(59, 130, 246, 0.15); color: #2563eb; }
    [data-theme="dark"] .status-in_progress { color: #93c5fd; }
    
    .status-completed { background: rgba(16, 185, 129, 0.15); color: #059669; }
    [data-theme="dark"] .status-completed { color: #6ee7b7; }

    .order-items { margin-bottom: 1.5rem; }

    .order-item {
        display: flex; justify-content: space-between; align-items: center;
        padding: 0.75rem 0; border-bottom: 1px dashed var(--border);
    }
    .order-item:last-child { border-bottom: none; }

    .item-name { font-weight: 600; color: var(--txt1); display: flex; align-items: center; gap: 0.5rem; }
    .item-qty { background: var(--surface); padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.8rem; font-weight: 700; color: var(--primary-vibrant); border: 1px solid var(--border); }
    .item-price { font-weight: 700; color: var(--txt1); }

    .order-footer {
        display: flex; justify-content: space-between; align-items: center;
        padding-top: 1rem; border-top: 1px solid var(--border);
    }

    .order-total-label { font-size: 0.875rem; color: var(--txt2); font-weight: 600; text-transform: uppercase; }
    .order-total-value { font-size: 1.5rem; font-weight: 800; color: var(--txt1); }

    .order-actions { display: flex; gap: 0.75rem; }

    .btn-action {
        padding: 0.6rem 1.25rem; border-radius: var(--border-radius-sm);
        font-weight: 600; font-size: 0.875rem; transition: var(--transition);
        text-decoration: none; display: inline-flex; align-items: center; gap: 0.5rem;
    }
    .btn-view { background: var(--surface); color: var(--txt1); border: 1px solid var(--border); }
    .btn-view:hover { background: var(--bg); border-color: var(--primary-vibrant); color: var(--primary-vibrant); }
    
    .btn-edit { background: rgba(59, 130, 246, 0.1); color: var(--info-vibrant); border: 1px solid rgba(59, 130, 246, 0.2); }
    .btn-edit:hover { background: var(--info-vibrant); color: white; }

    .summary-card {
        background: var(--surface); border-radius: var(--border-radius-lg);
        box-shadow: var(--card-shadow-soft); border: 1px solid var(--border);
        padding: 2rem; position: sticky; top: 2rem;
    }

    .summary-header { margin-bottom: 2rem; display: flex; align-items: center; gap: 0.75rem; }
    .summary-header h3 { font-size: 1.25rem; font-weight: 800; color: var(--txt1); margin: 0; }
    .summary-header i { color: var(--primary-vibrant); font-size: 1.5rem; }

    .summary-stats { display: flex; flex-direction: column; gap: 1rem; }
    
    .stat-row {
        display: flex; justify-content: space-between; align-items: center;
        padding-bottom: 1rem; border-bottom: 1px solid var(--border);
    }
    .stat-row:last-child { border-bottom: none; padding-bottom: 0; }

    .stat-label { color: var(--txt2); font-size: 0.9rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    .stat-value { font-size: 1.1rem; font-weight: 800; color: var(--txt1); }
    .stat-value.highlight { font-size: 1.8rem; color: var(--success-vibrant); }

    .print-bill-btn {
        display: flex; justify-content: center; align-items: center; gap: 0.5rem;
        width: 100%; margin-top: 2rem; padding: 1rem;
        background: var(--surface); color: var(--txt1);
        border: 2px solid var(--border); border-radius: var(--border-radius);
        font-weight: 700; font-size: 1rem; transition: var(--transition); cursor: pointer;
    }
    .print-bill-btn:hover { background: var(--bg); border-color: var(--primary-vibrant); color: var(--primary-vibrant); }

    .checkout-btn {
        display: flex; justify-content: center; align-items: center; gap: 0.5rem;
        width: 100%; margin-top: 1rem; padding: 1rem;
        background: linear-gradient(135deg, var(--success-vibrant) 0%, #059669 100%);
        color: white; border: none; border-radius: var(--border-radius);
        font-weight: 800; font-size: 1.1rem; transition: var(--transition); cursor: pointer;
        box-shadow: var(--success-vibrant-glow); text-transform: uppercase; letter-spacing: 0.05em;
        text-decoration: none;
    }
    .checkout-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(16, 185, 129, 0.6); }

    @media (max-width: 1024px) {
        .main-grid { grid-template-columns: 1fr; }
        .summary-card { position: static; margin-top: 2rem; }
    }
    @media (max-width: 768px) {
        .page-header { flex-direction: column; align-items: flex-start; gap: 1rem; padding: 1.5rem; }
        .page-title { font-size: 1.5rem; }
        .order-footer { flex-direction: column; gap: 1rem; align-items: flex-start; }
        .order-actions { width: 100%; }
        .btn-action { flex: 1; justify-content: center; }
    }
</style>"""

content = re.sub(r'<style>.*?</style>', new_css, content, flags=re.DOTALL)
with open('c:\\Intel\\hotela\\pos\\templates\\pos\\table_detail.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated table detail CSS")
