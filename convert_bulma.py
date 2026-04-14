import os
import re

directory = "c:/Users/Administrator/PycharmProjects/hotela"

# Basic mapping of Bulma classes to Tailwind classes
mapping = {
    # Layout
    'container': 'container mx-auto px-4 lg:max-w-7xl',
    'columns': 'flex flex-wrap -mx-3',
    'column': 'w-full px-3',
    'is-half': 'md:w-1/2',
    'is-one-third': 'md:w-1/3',
    'is-two-thirds': 'md:w-2/3',
    'is-one-quarter': 'md:w-1/4',
    'is-three-quarters': 'md:w-3/4',
    'is-offset-one-quarter': 'md:ml-[25%]',
    'is-offset-one-third': 'md:ml-[33.33%]',
    'is-full': 'w-full',
    
    # Box & Card
    'box': 'bg-white rounded-lg shadow-md p-6 mb-4',
    'card': 'bg-white rounded-lg shadow-md overflow-hidden',
    'card-header': 'border-b border-gray-200 px-6 py-4 flex items-center justify-between',
    'card-header-title': 'text-lg font-bold text-gray-800',
    'card-content': 'p-6',
    'card-footer': 'border-t border-gray-200 bg-gray-50 flex',
    'card-footer-item': 'flex-1 text-center py-3 text-blue-600 hover:bg-gray-100',
    
    # Typography
    'title': 'text-2xl font-bold text-gray-900 mb-4',
    'subtitle': 'text-lg text-gray-600 mb-4',
    'is-size-1': 'text-5xl font-extrabold',
    'is-size-2': 'text-4xl font-bold',
    'is-size-3': 'text-3xl font-bold',
    'is-size-4': 'text-2xl font-semibold',
    'is-size-5': 'text-xl font-medium',
    'is-size-6': 'text-base',
    'has-text-centered': 'text-center',
    'has-text-right': 'text-right',
    'has-text-left': 'text-left',
    'has-text-primary': 'text-[#1e3a8a]', # Replace with your original primary hex
    'has-text-info': 'text-blue-500',
    'has-text-success': 'text-green-500',
    'has-text-warning': 'text-yellow-500',
    'has-text-danger': 'text-red-500',

    # Buttons
    'button': 'inline-flex items-center justify-center px-4 py-2 border border-transparent rounded-md font-semibold focus:outline-none transition ease-in-out duration-150',
    'is-primary': 'bg-blue-600 hover:bg-blue-700 text-white',
    'is-link': 'bg-indigo-600 hover:bg-indigo-700 text-white',
    'is-info': 'bg-sky-500 hover:bg-sky-600 text-white',
    'is-success': 'bg-green-600 hover:bg-green-700 text-white',
    'is-warning': 'bg-yellow-500 hover:bg-yellow-600 text-black',
    'is-danger': 'bg-red-600 hover:bg-red-700 text-white',
    'is-small': 'text-xs px-2.5 py-1.5',
    'is-medium': 'text-lg px-6 py-3',
    'is-large': 'text-xl px-8 py-4',
    'is-outlined': 'bg-transparent border-2',
    
    # Navigation/Hero
    'navbar': 'bg-white shadow-sm w-full top-0',
    'hero': 'bg-gray-100 py-12',
    'hero-body': 'container mx-auto px-4',
    
    # Forms
    'field': 'mb-4',
    'label': 'block text-sm font-medium text-gray-700 mb-1',
    'control': 'relative',
    'input': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm border p-2',
    'textarea': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm border p-2',
    'select': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md border',
    'is-grouped': 'flex space-x-2',
    
    # Tables
    'table': 'min-w-full divide-y divide-gray-200',
    'is-striped': 'bg-white', # Using tailwind even/odd children works better in standard css
    'is-hoverable': 'hover:bg-gray-50',
    'is-bordered': 'border-collapse border border-gray-200',
    
    # Tags
    'tag': 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
    'tags': 'flex flex-wrap gap-2',
}

def convert_class_string(class_str, match):
    original_classes = class_str.split()
    new_classes = []
    
    for cls in original_classes:
        # Check mapping
        if cls in mapping:
            new_classes.extend(mapping[cls].split())
        else:
            new_classes.append(cls)
            
    # Remove duplicates but maintain order (mostly)
    seen = set()
    deduped = []
    for cls in new_classes:
        if cls not in seen:
            seen.add(cls)
            deduped.append(cls)
            
    return 'class="' + ' '.join(deduped) + '"'

modified_count = 0
for root, _, files in os.walk(directory):
    for f in files:
        if f.endswith('.html'):
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Simple regex to find class attributes string
            def repl(match):
                class_content = match.group(1)
                return convert_class_string(class_content, match)
                
            new_content = re.sub(r'class="([^"]*)"', repl, content)
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                modified_count += 1
                
print(f"Modified {modified_count} templates.")
