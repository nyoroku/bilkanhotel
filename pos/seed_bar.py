import os
import django
import sys

# Set up Django environment
sys.path.append('c:\\Intel\\hotela')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotela.settings')
django.setup()

from pos.models import Category, MenuItem, Supplier

def seed_bar_data():
    print("Starting Bar seeding...")

    # 1. Create Bar categories
    categories_data = [
        ("Beers", "Bar"),
        ("Whiskeys", "Bar"),
        ("Vodkas", "Bar"),
        ("Gins", "Bar"),
        ("Wines", "Bar"),
        ("Soft Drinks", "Bar"),
        ("Cocktails", "Bar"),
        ("Bar Snacks", "Bar"),
    ]

    categories = {}
    for name, module in categories_data:
        cat, created = Category.objects.get_or_create(name=name, module=module)
        categories[name] = cat
        if created:
            print(f"Created category: {name}")

    # 2. Create Menu Items
    menu_items_data = [
        # Beers
        ("Tusker Lager", "Beers", 300),
        ("Tusker Malt", "Beers", 350),
        ("Tusker Cider", "Beers", 350),
        ("White Cap", "Beers", 300),
        ("White Cap Crisp", "Beers", 320),
        ("Guinness FES 330ml", "Beers", 350),
        ("Heineken", "Beers", 450),
        
        # Whiskeys
        ("Jameson Irish Whiskey", "Whiskeys", 4500),
        ("Johnnie Walker Black Label", "Whiskeys", 6500),
        ("Johnnie Walker Red Label", "Whiskeys", 3500),
        ("Jack Daniels", "Whiskeys", 5500),
        ("Glenfiddich 12YR", "Whiskeys", 9500),
        
        # Vodkas
        ("Smirnoff Red", "Vodkas", 2500),
        ("Ciroc Blue Stone", "Vodkas", 7500),
        ("Absolut Vodka", "Vodkas", 3500),
        
        # Gins
        ("Gilbeys Special Dry Gin", "Gins", 2200),
        ("Gordon's London Dry", "Gins", 3000),
        ("Tanqueray London Dry", "Gins", 4500),
        ("Hendrick's Gin", "Gins", 8500),
        
        # Wines
        ("Frontera Cabernet Sauvignon", "Wines", 2500),
        ("Frontera Sauvignon Blanc", "Wines", 2500),
        ("Robertson Natural Sweet Red", "Wines", 2800),
        ("Casillero del Diablo", "Wines", 4000),
        
        # Soft Drinks
        ("Coca Cola 300ml", "Soft Drinks", 100),
        ("Fanta Orange 300ml", "Soft Drinks", 100),
        ("Sprite 300ml", "Soft Drinks", 100),
        ("Stoney Tangawizi", "Soft Drinks", 100),
        ("Dasani Water 500ml", "Soft Drinks", 80),
        ("Minute Maid Orange", "Soft Drinks", 150),
        
        # Cocktails
        ("Mojito", "Cocktails", 850),
        ("Margarita", "Cocktails", 850),
        ("Old Fashioned", "Cocktails", 950),
        ("Long Island Iced Tea", "Cocktails", 1100),
        ("Whiskey Sour", "Cocktails", 850),
        
        # Snacks
        ("Salted Peanuts", "Bar Snacks", 150),
        ("Potato Crisps", "Bar Snacks", 200),
        ("Mixed Nuts", "Bar Snacks", 350),
    ]

    for name, cat_name, price in menu_items_data:
        item, created = MenuItem.objects.get_or_create(
            name=name.upper(),
            category=categories[cat_name],
            defaults={
                'selling_price': price,
                'stock_quantity': 100, # Default stock
                'is_active': True
            }
        )
        if created:
            print(f"Created item: {name}")
        else:
            # Update price if item already exists
            item.selling_price = price
            item.save()
            print(f"Updated price for item: {name}")

    print("Bar seeding complete!")

if __name__ == "__main__":
    seed_bar_data()
