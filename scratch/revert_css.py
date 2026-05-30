import re

path = r'c:\Users\Giap\OneDrive - Industrial University of HoChiMinh City\Desktop\Tool_report_V4\AEON_tool_report\AEON _ Tool report V4\rmc-assistant-v4\frontend\assets\style.css'
with open(path, 'r', encoding='utf-8') as f:
    css = f.read()

# Root
css = re.sub(
    r':root \{.*?--transition:\s*200ms cubic-bezier\(0\.4, 0, 0\.2, 1\);\s*\}',
    ':root {\n  --bg-base:       #0f1117;\n  --bg-panel:      #171b24;\n  --bg-card:       #1e2330;\n  --bg-hover:      #252c3d;\n  --bg-active:     #2a3350;\n  --border:        #2e3548;\n  --border-light:  #3a4258;\n  --text-primary:  #e8ecf4;\n  --text-secondary:#8a92a6;\n  --text-muted:    #555e72;\n  --accent:        #3b82f6;\n  --accent-hover:  #2563eb;\n  --accent-dim:    rgba(59,130,246,0.15);\n  --green:         #22c55e;\n  --green-dim:     rgba(34,197,94,0.15);\n  --orange:        #f97316;\n  --orange-dim:    rgba(249,115,22,0.15);\n  --red:           #ef4444;\n  --red-dim:       rgba(239,68,68,0.15);\n  --pink:          #ef3eb3;\n  --pink-dim:      rgba(239,62,179,0.15);\n  --teal:          #14b8a6;\n  --teal-dim:      rgba(20,184,166,0.15);\n  --purple:        #a855f7;\n  --purple-dim:    rgba(168,85,247,0.15);\n  --font-sans:    \'IBM Plex Sans\', sans-serif;\n  --font-mono:    \'IBM Plex Mono\', monospace;\n  --radius-sm:    4px;\n  --radius:       8px;\n  --radius-lg:    12px;\n  --transition:   150ms ease;\n}',
    css, flags=re.DOTALL
)

# Topbar
css = re.sub(
    r'#topbar \{[^}]*backdrop-filter:[^}]*\}',
    '#topbar {\n  grid-column: 1 / -1;\n  background: var(--bg-panel);\n  border-bottom: 1px solid var(--border);\n  display: flex;\n  align-items: center;\n  padding: 0 16px;\n  gap: 10px;\n  z-index: 100;\n  transition: background var(--transition), border-color var(--transition);\n}',
    css
)

# Topbar btn
css = re.sub(
    r'\.topbar-btn \{[^}]*transition: all 0\.2s ease;[^}]*\}\s*\.topbar-btn:hover \{[^}]*\}\s*\.topbar-btn\.active \{[^}]*\}',
    '.topbar-btn {\n  background: var(--bg-card);\n  border: 1px solid var(--border);\n  color: var(--text-secondary);\n  padding: 4px 12px;\n  border-radius: var(--radius-sm);\n  cursor: pointer;\n  font-family: var(--font-sans);\n  font-size: 12px;\n  transition: var(--transition);\n  white-space: nowrap;\n}\n.topbar-btn:hover { background: var(--bg-hover); color: var(--text-primary); }\n.topbar-btn.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }',
    css
)

# Sidebar
css = re.sub(
    r'#sidebar \{[^}]*backdrop-filter:[^}]*\}',
    '#sidebar {\n  background: var(--bg-panel);\n  border-right: 1px solid var(--border);\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n  transition: background var(--transition), border-color var(--transition);\n}',
    css
)

# Main
css = re.sub(
    r'#main \{[^}]*linear-gradient[^}]*\}',
    '#main {\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n  background: var(--bg-base);\n  transition: background var(--transition);\n}',
    css
)

# Strip btn
css = re.sub(
    r'\.strip-btn \{[^}]*box-shadow:[^}]*\}\s*\.strip-btn:hover \{[^}]*\}\s*\.strip-btn\.confirm-btn \{[^}]*\}\s*\.strip-btn\.confirm-btn:hover \{[^}]*\}',
    '.strip-btn {\n  padding: 7px 14px;\n  border-radius: var(--radius-sm);\n  border: 1px solid var(--border);\n  font-family: var(--font-sans);\n  font-size: 12px;\n  font-weight: 500;\n  cursor: pointer;\n  transition: var(--transition);\n  background: var(--bg-card);\n  color: var(--text-secondary);\n}\n.strip-btn:hover { color: var(--text-primary); background: var(--bg-hover); }\n.strip-btn.confirm-btn { color: var(--green); border-color: var(--green); }\n.strip-btn.confirm-btn:hover { background: var(--green-dim); }',
    css
)

# Modal
css = re.sub(
    r'\.modal \{[^}]*animation: modalSlideIn[^}]*\}\s*@keyframes modalSlideIn \{[^}]*\}',
    '.modal {\n  background: var(--bg-panel);\n  border: 1px solid var(--border-light);\n  border-radius: var(--radius-lg);\n  padding: 24px;\n  min-width: 480px;\n  max-width: 640px;\n  width: 90%;\n  max-height: 90vh;\n  overflow-y: auto;\n  display: flex;\n  flex-direction: column;\n  gap: 16px;\n  scrollbar-width: thin;\n  scrollbar-color: var(--border) transparent;\n  transition: background var(--transition), border-color var(--transition);\n}',
    css
)

# Form group
css = re.sub(
    r'\.form-group input,\s*\.form-group select,\s*\.form-group textarea \{[^}]*\}\s*\.form-group input:focus,\s*\.form-group select:focus,\s*\.form-group textarea:focus \{[^}]*\}\s*\.form-group textarea \{[^}]*\}\s*\.form-group select option \{[^}]*\}',
    '.form-group input,\n.form-group select,\n.form-group textarea {\n  background: var(--bg-card);\n  border: 1px solid var(--border);\n  border-radius: var(--radius-sm);\n  color: var(--text-primary);\n  font-family: var(--font-sans);\n  font-size: 13px;\n  padding: 7px 10px;\n  outline: none;\n  transition: var(--transition);\n}\n.form-group input:focus,\n.form-group select:focus,\n.form-group textarea:focus { border-color: var(--border-light); }\n.form-group textarea { resize: vertical; min-height: 80px; }\n.form-group select option { background: var(--bg-card); color: var(--text-primary); }',
    css
)

# Btn Primary / Secondary
css = re.sub(
    r'\.btn-primary \{[^}]*linear-gradient[^}]*\}\s*\.btn-primary:hover \{[^}]*\}\s*\.btn-secondary \{[^}]*\}\s*\.btn-secondary:hover \{[^}]*\}',
    '.btn-primary {\n  padding: 7px 20px;\n  border-radius: var(--radius-sm);\n  border: none;\n  background: var(--accent);\n  color: #fff;\n  font-family: var(--font-sans);\n  font-size: 13px;\n  font-weight: 500;\n  cursor: pointer;\n  transition: var(--transition);\n}\n.btn-primary:hover { background: var(--accent-hover); }\n.btn-secondary {\n  padding: 7px 20px;\n  border-radius: var(--radius-sm);\n  border: 1px solid var(--border);\n  background: var(--bg-card);\n  color: var(--text-secondary);\n  font-family: var(--font-sans);\n  font-size: 13px;\n  cursor: pointer;\n  transition: var(--transition);\n}\n.btn-secondary:hover { background: var(--bg-hover); color: var(--text-primary); }',
    css
)

# Table
css = re.sub(
    r'\.note-table-wrap \{[^}]*\}\s*table \{[^}]*\}\s*thead th \{[^}]*backdrop-filter:[^}]*\}\s*tbody tr \{[^}]*\}\s*tbody tr:last-child \{[^}]*\}\s*tbody tr:hover \{[^}]*\}\s*tbody td \{[^}]*\}',
    '.note-table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); }\ntable { width: 100%; border-collapse: collapse; }\nthead th {\n  background: var(--bg-card);\n  padding: 8px 10px;\n  text-align: left;\n  font-size: 11px;\n  font-weight: 600;\n  letter-spacing: 0.06em;\n  text-transform: uppercase;\n  color: var(--text-muted);\n  border-bottom: 1px solid var(--border);\n}\ntbody tr { border-bottom: 1px solid var(--border); transition: background var(--transition); }\ntbody tr:last-child { border-bottom: none; }\ntbody tr:hover { background: var(--bg-hover); }\ntbody td { padding: 7px 10px; font-size: 12px; color: var(--text-secondary); }',
    css
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(css)
print("Done")
