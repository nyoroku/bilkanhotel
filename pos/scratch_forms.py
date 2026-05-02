import re

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Enhance the form input overrides
new_form_styles = """
    /* ── SUPER PREMIUM FORMS ── */
    input[type="text"], input[type="email"], input[type="password"], input[type="number"], input[type="search"], select, textarea, .form-input, .input, .textarea {
        width: 100% !important;
        padding: 0.85rem 1.25rem !important;
        border-radius: 12px !important;
        font-size: 0.95rem !important;
        font-family: 'Inter', sans-serif !important;
        background: rgba(15, 23, 42, 0.6) !important;
        color: #f8fafc !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        outline: none !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        backdrop-filter: blur(12px) !important;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.2) !important;
    }
    input:focus, select:focus, textarea:focus, .form-input:focus, .input:focus {
        border-color: #8b5cf6 !important;
        box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.25), inset 0 2px 4px rgba(0,0,0,0.2) !important;
        background: rgba(15, 23, 42, 0.8) !important;
        transform: translateY(-1px);
    }
    ::placeholder { color: #94a3b8 !important; opacity: 1 !important; font-weight: 500; }
    label, .label, .form-label {
        display: block !important;
        font-size: 0.8rem !important;
        font-weight: 700 !important;
        color: #cbd5e1 !important;
        margin-bottom: 0.5rem !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }
    /* Select dropdown styling */
    select {
        appearance: none !important;
        background-image: url("data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22292.4%22%20height%3D%22292.4%22%3E%3Cpath%20fill%3D%22%23cbd5e1%22%20d%3D%22M287%2069.4a17.6%2017.6%200%200%200-13-5.4H18.4c-5%200-9.3%201.8-12.9%205.4A17.6%2017.6%200%200%200%200%2082.2c0%205%201.8%209.3%205.4%2012.9l128%20127.9c3.6%203.6%207.8%205.4%2012.8%205.4s9.2-1.8%2012.8-5.4L287%2095c3.5-3.5%205.4-7.8%205.4-12.8%200-5-1.9-9.2-5.5-12.8z%22%2F%3E%3C%2Fsvg%3E") !important;
        background-repeat: no-repeat !important;
        background-position: right 1rem top 50% !important;
        background-size: 0.65rem auto !important;
    }
    select option {
        background: #0f172a !important;
        color: #f8fafc !important;
        padding: 10px !important;
    }
"""

content = re.sub(r'/\*\s*──\s*FORMS\s*──\s*\*/.*?(?=/\*\s*──)', new_form_styles, content, flags=re.DOTALL)

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\base.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated forms in base.html")
