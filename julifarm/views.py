from django.shortcuts import render, get_object_or_404
from django.utils import timezone  # Add this import
from .models import MenuCategory, MenuItem, Event, Career, Blog


def food_menu(request):
    # Get all food categories (where category_type is 'food')
    food_categories = MenuCategory.objects.filter(
        category_type=MenuCategory.FOOD
    ).prefetch_related('items')

    context = {
        'categories': food_categories,
        'page_title': 'Food Menu',
        'page_description': 'Perfectly grilled meat, prepared the traditional Kenyan way. Our secret spice blend and slow-cooking technique creates flavors that will transport you.'
    }
    return render(request, 'menu/food.html', context)


def drinks_menu(request):
    # Get all drink categories (where category_type is 'drink')
    drink_categories = MenuCategory.objects.filter(
        category_type=MenuCategory.DRINK
    ).prefetch_related('items')

    context = {
        'categories': drink_categories,
        'page_title': 'Drinks Menu',
        'page_description': 'From ice-cold local brews to expertly crafted cocktails and fresh tropical juices, we have the perfect drink to complement every meal and moment.'
    }
    return render(request, 'menu/drinks.html', context)


def events(request):
    upcoming_events = Event.objects.filter(date__gte=timezone.now()).order_by('date')
    past_events = Event.objects.filter(date__lt=timezone.now()).order_by('-date')[:5]  # Show 5 most recent past events

    context = {
        'upcoming_events': upcoming_events,
        'past_events': past_events,
        'page_title': 'Live Entertainment',
        'page_description': 'Enjoy live bands every weekend, catch the game on our big screens, and join our special themed nights that bring the community together.'
    }
    return render(request, 'menu/events.html', context)


def event_detail(request, slug):
    event = get_object_or_404(Event, slug=slug)
    context = {
        'event': event,
        'page_title': event.title
    }
    return render(request, 'menu/event_detail.html', context)





