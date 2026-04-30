from django.db import models
from django.utils.text import slugify
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from ckeditor.fields import RichTextField
from tinymce.models import HTMLField


class MenuCategory(models.Model):
    FOOD = 'food'
    DRINK = 'drink'
    CATEGORY_TYPES = [
        (FOOD, 'Food'),
        (DRINK, 'Drink'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    slug = models.SlugField(unique=True, blank=True)
    image = models.ImageField(upload_to='menu_categories/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    category_type = models.CharField(
        max_length=10,
        choices=CATEGORY_TYPES,
        default=FOOD,
    )

    class Meta:
        verbose_name_plural = "Menu Categories"
        ordering = ['display_order']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class MenuItem(models.Model):
    category = models.ForeignKey(MenuCategory, related_name='items', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order']

    def __str__(self):
        return self.name


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to='events/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['date']


class Blog(models.Model):
    title = models.CharField(max_length=100, blank=True)
    picture = ProcessedImageField(upload_to='blogs', processors=[ResizeToFill(200, 200)],
                                  format='JPEG',
                                  options={'quality': 100}, blank=True)
    summary = HTMLField()
    body = HTMLField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Career(models.Model):
    STATUS = (
        ('open', 'Open'),
        ('closed', 'Closed'),

    )
    title = models.CharField(max_length=200, blank=True)
    summary = HTMLField()
    description = HTMLField()
    created = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS, default='open')

    def __str__(self):
        return self.title


