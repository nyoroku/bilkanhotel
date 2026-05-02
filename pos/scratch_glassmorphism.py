import re

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\base.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_styles = """<style>
    /* ── POS PREMIUM GLASSMORPHISM DESIGN SYSTEM ── */
    :root, [data-theme="dark"], [data-theme="light"] {
        --bg: #0B0F19; /* Deep midnight blue */
        --surface: rgba(17, 24, 39, 0.7); /* Deep glass */
        --surface-hover: rgba(31, 41, 55, 0.8);
        --raised: rgba(31, 41, 55, 0.9);
        
        --border: rgba(255, 255, 255, 0.08);
        --border-hl: rgba(255, 255, 255, 0.15);
        
        --txt1: #f8fafc;
        --txt2: #cbd5e1;
        --txt3: #94a3b8;
        
        --primary: #6366f1; /* Vibrant Indigo */
        --primary-hover: #818cf8;
        --primary-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
        --primary-glow: 0 0 20px rgba(99, 102, 241, 0.4);
        
        --success: #10b981;
        --success-gradient: linear-gradient(135deg, #059669 0%, #10b981 100%);
        --warning: #f59e0b;
        --warning-gradient: linear-gradient(135deg, #d97706 0%, #f59e0b 100%);
        --error: #ef4444;
        --error-gradient: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
        --info: #3b82f6;
        
        --s1: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        --s2: 0 12px 48px 0 rgba(0, 0, 0, 0.4);
        --s3: 0 16px 64px 0 rgba(0, 0, 0, 0.5);
        
        --backdrop: blur(16px);
        
        /* legacy aliases kept for existing templates */
        --blue: #6366f1;
        --blue-lt: #818cf8;
        --gold: #f59e0b;
    }

    /* BASE */
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    html,body{height:100%}
    html{
        font-family:'Inter',system-ui,sans-serif;
        background:var(--bg) url('data:image/svg+xml;utf8,<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" fill="none"/><circle cx="20" cy="20" r="40" fill="rgba(99,102,241,0.03)" filter="blur(20px)"/><circle cx="80" cy="80" r="40" fill="rgba(168,85,247,0.02)" filter="blur(20px)"/></svg>') no-repeat center center fixed;
        background-size: cover;
        color:var(--txt1);
        -webkit-font-smoothing:antialiased;
        font-size:14px;
    }
    h1,h2,h3,h4,h5{font-family:'Inter',system-ui,sans-serif;color:var(--txt1);font-weight:600;letter-spacing:-0.02em}

    /* OVERRIDE TAILWIND/BULMA BACKGROUNDS */
    .bg-white, .has-background-white, .has-background-light, .is-light {
        background: var(--surface) !important;
        backdrop-filter: var(--backdrop) !important;
        color: var(--txt1) !important;
        border: 1px solid var(--border) !important;
    }
    .text-gray-900, .text-gray-800, .has-text-dark, .has-text-black { color: var(--txt1) !important; }
    .text-gray-600, .has-text-grey, .has-text-grey-light { color: var(--txt2) !important; }

    /* LAYOUT */
    .pos-shell{display:flex;min-height:100vh}
    .main-wrapper{flex-grow:1;display:flex;flex-direction:column;min-height:100vh;background:transparent;transition:background .3s}
    .main-content-area{flex-grow:1;padding:1.75rem;overflow-y:auto;color:var(--txt1)}

    /* SIDEBAR */
    .sidebar{
        width:256px;flex-shrink:0;display:flex;flex-direction:column;
        height:100vh;overflow-y:auto;position:sticky;top:0;
        background:rgba(11, 15, 25, 0.8);backdrop-filter:var(--backdrop);
        border-right:1px solid var(--border);
        box-shadow:var(--s1);
    }
    .sidebar-header{
        padding:1.5rem 1rem;border-bottom:1px solid var(--border);
        display:flex;align-items:center;justify-content:space-between;
    }
    .sidebar-logo{display:flex;align-items:center;gap:.6rem;text-decoration:none}
    .logo-icon{
        width:34px;height:34px;flex-shrink:0;border-radius:10px;
        background:var(--primary-gradient);
        box-shadow:var(--primary-glow);
        display:flex;align-items:center;justify-content:center;
        font-size:1rem;color:#fff;
    }
    .logo-text{font-family:'Inter',sans-serif;font-size:1rem;font-weight:800;color:#fff;letter-spacing:0}
    .logo-sub{display:block;font-size:.55rem;font-weight:600;letter-spacing:.15em;text-transform:uppercase;color:var(--txt3);margin-top:2px}

    .theme-toggle-btn{display:none;} /* Removed theme toggle, strictly premium dark */

    .sidebar-nav{padding:1rem .75rem;flex-grow:1;display:flex;flex-direction:column;gap:.25rem}
    .nav-label{font-size:.65rem;font-weight:700;color:var(--txt3);text-transform:uppercase;letter-spacing:.1em;margin:1rem 0 .5rem .5rem}
    
    .nav-item{
        display:flex;align-items:center;gap:.65rem;padding:.65rem .75rem;
        border-radius:8px;color:var(--txt2);text-decoration:none;font-weight:600;
        font-size:.85rem;transition:all .2s cubic-bezier(0.4, 0, 0.2, 1);
        position:relative;overflow:hidden;
    }
    .nav-item::before{
        content:'';position:absolute;left:0;top:0;bottom:0;width:3px;
        background:var(--primary-gradient);opacity:0;transition:opacity .2s;
        border-radius:0 3px 3px 0;
    }
    .nav-icon{font-size:1rem;width:24px;text-align:center;transition:color .2s}
    .nav-item:hover{background:var(--surface);color:var(--txt1);transform:translateX(2px)}
    .nav-item.active{background:var(--surface-hover);color:var(--txt1);box-shadow:inset 0 1px 0 var(--border)}
    .nav-item.active::before{opacity:1}
    .nav-item.active .nav-icon{color:var(--primary)}

    .sidebar-footer{padding:1rem;border-top:1px solid var(--border);background:rgba(0,0,0,0.2)}
    .user-profile{display:flex;align-items:center;gap:.75rem}
    .user-avatar{width:36px;height:36px;border-radius:50%;background:var(--primary-gradient);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:1rem;box-shadow:var(--primary-glow)}
    .user-info{overflow:hidden}
    .user-name{font-size:.85rem;font-weight:700;color:var(--txt1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .user-role{font-size:.65rem;color:var(--txt3);text-transform:uppercase;letter-spacing:.05em;font-weight:600}

    /* MOBILE NAV */
    .mobile-nav{display:none;background:rgba(11, 15, 25, 0.9);backdrop-filter:var(--backdrop);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:1000;box-shadow:var(--s1)}
    .mobile-nav-inner{display:flex;align-items:center;justify-content:space-between;padding:.75rem 1.25rem}
    .mobile-menu-btn{background:transparent;border:none;color:var(--txt1);font-size:1.25rem;cursor:pointer}
    #mobile-nav-menu{display:none;position:absolute;top:100%;left:0;width:100%;background:var(--bg);border-bottom:1px solid var(--border);box-shadow:var(--s3);max-height:80vh;overflow-y:auto;z-index:999}
    #mobile-nav-menu.is-active{display:block}
    @media(max-width:1024px){.sidebar{display:none}.mobile-nav{display:block}.main-content-area{padding:1rem}}
    @media(max-width:640px){.main-content-area{padding:.75rem}}

    /* ── GLOBAL BUTTONS ── */
    .btn, .button{
        display:inline-flex;align-items:center;justify-content:center;gap:.5rem;
        padding:.6rem 1.2rem;border-radius:10px;font-size:.85rem;font-weight:700;
        font-family:'Inter',sans-serif;cursor:pointer;border:none;
        text-decoration:none;transition:all .3s cubic-bezier(0.4, 0, 0.2, 1);
        position:relative;overflow:hidden;
    }
    .btn::after, .button::after{content:'';position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(rgba(255,255,255,.1),transparent);opacity:0;transition:opacity .2s;}
    .btn:hover::after, .button:hover::after{opacity:1}
    
    .btn-primary, .button.is-primary{background:var(--primary-gradient) !important;color:#fff !important;border:none !important;box-shadow:var(--primary-glow) !important;}
    .btn-primary:hover, .button.is-primary:hover{transform:translateY(-2px);box-shadow:0 0 25px rgba(99,102,241,.6) !important;}
    .btn-primary:active, .button.is-primary:active{transform:translateY(1px);box-shadow:var(--primary-glow) !important;}
    
    .btn-secondary, .button.is-light{background:var(--surface) !important;color:var(--txt1) !important;border:1px solid var(--border) !important;box-shadow:var(--s1) !important;}
    .btn-secondary:hover, .button.is-light:hover{background:var(--surface-hover) !important;border-color:var(--border-hl) !important;transform:translateY(-2px);}
    
    .btn-danger, .button.is-danger{background:var(--error-gradient) !important;color:#fff !important;border:none !important;box-shadow:0 0 20px rgba(239,68,68,.3) !important;}
    .btn-danger:hover, .button.is-danger:hover{transform:translateY(-2px);box-shadow:0 0 25px rgba(239,68,68,.5) !important;}

    /* ── FORMS ── */
    .form-input, .input, .select select, .textarea {
        width:100%;padding:.75rem 1rem;border-radius:10px;font-size:.9rem;
        font-family:'Inter',sans-serif;background:var(--surface) !important;color:var(--txt1) !important;
        border:1px solid var(--border) !important;outline:none;
        transition:all .2s;backdrop-filter:var(--backdrop);
    }
    .form-input:focus, .input:focus, .select select:focus, .textarea:focus {border-color:var(--primary) !important;box-shadow:0 0 0 4px rgba(99,102,241,.2) !important;background:var(--surface-hover) !important;}
    .form-input::placeholder, .input::placeholder, .textarea::placeholder{color:var(--txt3) !important;}
    .form-label, .label{display:block;font-size:.75rem;font-weight:700;color:var(--txt2) !important;margin-bottom:.4rem;letter-spacing:.03em;text-transform:uppercase;}

    /* ── CARDS & COMPONENTS ── */
    .bh-card, .card, .box{background:var(--surface) !important;backdrop-filter:var(--backdrop) !important;border:1px solid var(--border) !important;border-radius:16px !important;box-shadow:var(--s2) !important;}

    /* ── BADGES ── */
    .badge, .tag{display:inline-flex;align-items:center;padding:.2rem .6rem;border-radius:6px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;}
    .badge-primary, .tag.is-primary{background:rgba(99,102,241,.15) !important;color:#818cf8 !important;border:1px solid rgba(99,102,241,.3) !important;}
    .badge-success, .tag.is-success{background:rgba(16,185,129,.15) !important;color:#34d399 !important;border:1px solid rgba(16,185,129,.3) !important;}
    .badge-warning, .tag.is-warning{background:rgba(245,158,11,.15) !important;color:#fbbf24 !important;border:1px solid rgba(245,158,11,.3) !important;}
    .badge-error, .tag.is-danger{background:rgba(239,68,68,.15) !important;color:#f87171 !important;border:1px solid rgba(239,68,68,.3) !important;}

    /* ── PAGE HEADER ── */
    .page-hdr{background:var(--surface);backdrop-filter:var(--backdrop);border:1px solid var(--border);border-radius:16px;padding:2rem 2.5rem;margin-bottom:2rem;display:flex;align-items:center;justify-content:space-between;gap:1.5rem;flex-wrap:wrap;box-shadow:var(--s2);position:relative;overflow:hidden}
    .page-hdr::before{content:'';position:absolute;top:-50px;left:-50px;width:150px;height:150px;background:var(--primary);filter:blur(80px);opacity:.2;pointer-events:none}
    .page-hdr h1{font-size:1.8rem;font-weight:800;color:var(--txt1);margin:0;display:flex;align-items:center;gap:1rem;position:relative}
    .page-hdr-sub{font-size:.9rem;color:var(--txt2);margin-top:.4rem;position:relative}
    .page-hdr-actions{display:flex;gap:.75rem;flex-wrap:wrap;position:relative}

    /* ── KPI / STAT GRID ── */
    .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1.5rem;margin-bottom:2rem}
    .kpi-card{background:var(--surface);backdrop-filter:var(--backdrop);border:1px solid var(--border);border-radius:16px;padding:1.5rem;box-shadow:var(--s2);transition:all .3s cubic-bezier(0.4, 0, 0.2, 1);position:relative;overflow:hidden}
    .kpi-card:hover{transform:translateY(-5px);border-color:var(--border-hl);box-shadow:var(--s3)}
    .kpi-ico{width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1.25rem;margin-bottom:1rem;color:#fff;box-shadow:var(--s1)}
    .kpi-ico--primary{background:var(--primary-gradient)}
    .kpi-ico--success{background:var(--success-gradient)}
    .kpi-ico--warning{background:var(--warning-gradient)}
    .kpi-ico--error{background:var(--error-gradient)}
    .kpi-ico--info{background:linear-gradient(135deg,#3b82f6 0%,#60a5fa 100%)}
    .kpi-lbl{font-size:.75rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--txt3);margin-bottom:.4rem}
    .kpi-val{font-size:2rem;font-weight:800;color:var(--txt1);line-height:1}

    /* ── DATA TABLE ── */
    .tbl-card{background:var(--surface);backdrop-filter:var(--backdrop);border:1px solid var(--border);border-radius:16px;box-shadow:var(--s2);overflow:hidden}
    .ds-table, .table{width:100%;border-collapse:collapse;font-size:.9rem;background:transparent !important;color:var(--txt1) !important;}
    .ds-table thead th, .table thead th{text-align:left;padding:1rem 1.25rem;font-size:.75rem;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--txt3) !important;border-bottom:1px solid var(--border) !important;background:rgba(0,0,0,.2) !important;}
    .ds-table tbody td, .table tbody td{padding:1rem 1.25rem;border-bottom:1px solid var(--border) !important;color:var(--txt1) !important;vertical-align:middle;}
    .ds-table tbody tr, .table tbody tr{transition:background .2s;}
    .ds-table tbody tr:hover, .table tbody tr:hover{background:rgba(255,255,255,.03) !important;}
    
    /* ── MODULE GRID ── */
    .mod-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1.5rem;margin-bottom:2rem}
    .mod-card{background:var(--surface);backdrop-filter:var(--backdrop);border:1px solid var(--border);border-radius:16px;padding:2rem 1.5rem;text-align:center;text-decoration:none;display:flex;flex-direction:column;align-items:center;transition:all .3s cubic-bezier(0.4, 0, 0.2, 1);box-shadow:var(--s2)}
    .mod-card:hover{transform:translateY(-5px) scale(1.02);border-color:var(--primary);box-shadow:var(--primary-glow)}
    .mod-ico{width:64px;height:64px;border-radius:16px;background:var(--raised);color:var(--primary);font-size:1.75rem;display:flex;align-items:center;justify-content:center;margin-bottom:1.25rem;transition:all .3s;box-shadow:var(--s1)}
    .mod-card:hover .mod-ico{background:var(--primary-gradient);color:#fff;box-shadow:0 8px 24px rgba(99,102,241,.4)}
    .mod-card h3{font-size:1.1rem;font-weight:700;color:var(--txt1);margin-bottom:.4rem}
    .mod-card p{font-size:.8rem;color:var(--txt3);margin:0}
</style>"""

content = re.sub(r'<style>.*?</style>', new_styles, content, flags=re.DOTALL)

with open('c:\\Intel\\hotela\\pos\\templates\\pos\\base.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated base.html styles to ultra premium glassmorphism.")
