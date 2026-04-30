import os
import re

directory = "c:/Users/Administrator/PycharmProjects/hotela"

tailwind_script = '<script src="https://cdn.tailwindcss.com"></script>\n'
sweetalert = '<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>\n'

for root, _, files in os.walk(directory):
    for f in files:
        if f.endswith('base.html'):
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            if "tailwindcss.com" not in content and "</head>" in content:
                # Basic colors config
                tailwind_config = """
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          primary: '#1e3a8a', 
          blue: {
            600: '#1e3a8a',
            700: '#172554'
          }
        }
      }
    }
  }
</script>
"""
                content = content.replace("</head>", f"{tailwind_script}{tailwind_config}</head>")
                
            # Remove bulma css link if exists
            content = re.sub(r'<link[^>]*bulma[^>]*>', '', content)
            
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(content)


