import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password


class UserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifier
    for authentication instead of usernames.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model with PIN login functionality.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('room_manager', 'Room Manager'),
        ('waiter', 'Waiter'),
        ('bar_staff', 'Bar Staff'),
        ('butcher', 'Butcher'),
        ('cashier', 'Cashier'),
    ]

    # --- NEW FIELDS FOR PIN LOGIN AND PROFILE ---
    pin = models.CharField(max_length=128, blank=True, null=True,
                           help_text="A 4-6 digit PIN for quick POS login. Will be stored securely.")
    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True,
                                      help_text="Optional profile picture for the login screen.")
    # --- END OF NEW FIELDS ---

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=255, unique=True)
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                       help_text="The user's gross monthly salary.")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='waiter')
    employee_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    is_active_shift = models.BooleanField(default=False)
    waiter_reward_points = models.PositiveIntegerField(
        default=0,
        help_text="The waiter's current reward point balance.",
    )
    current_leaderboard_bonus = models.PositiveIntegerField(
        default=0,
        help_text="Current bonus points from leaderboard position (changes dynamically)"
    )

    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$',
                                 message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    # Custom related_name to resolve clashes with the default auth.User model
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name='custom_user_set',
        related_query_name='user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='custom_user_set',
        related_query_name='user',
    )

    def set_pin(self, raw_pin):
        """Hashes the raw PIN and saves it."""
        # Ensure pin is a string before hashing
        if raw_pin is not None:
            self.pin = make_password(str(raw_pin))

    def check_pin(self, raw_pin):
        """Checks a raw PIN against the stored hash."""
        if self.pin is None:
            return False
        return check_password(str(raw_pin), self.pin)

    def __str__(self):
        return self.get_full_name()

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self):
        return self.full_name or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]

    class Meta:
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['email']),
        ]


