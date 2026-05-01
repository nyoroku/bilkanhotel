# pos/models.py

from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from accounts.models import User
from pos.models import MenuItem


class Schedule(models.Model):
    """
    Represents a top-level work schedule, like 'July 2025 Schedule'.
    This acts as a container for multiple shifts over a period of time.
    """

    class Status(models.TextChoices):
        DRAFT = 'Draft', 'Draft'
        PUBLISHED = 'Published', 'Published'
    name = models.CharField(max_length=200, help_text="e.g., 'July Week 1', 'Weekend Schedule'")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError(_('End date cannot be before the start date.'))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Shift(models.Model):
    """
    A single shift (multi-day capable) that belongs to a Schedule.
    Example: Monday 22:00 → Tuesday 06:00
    """
    schedule = models.ForeignKey('Schedule', on_delete=models.CASCADE, related_name='shifts')
    name = models.CharField(max_length=200, help_text="e.g. 'Night', 'Morning', 'Bar'")
    start_datetime = models.DateTimeField(default=timezone.now)
    end_datetime = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['start_datetime']
        indexes = [models.Index(fields=['schedule', 'start_datetime'])]

    def clean(self):
        if self.start_datetime >= self.end_datetime:
            raise ValidationError('End must be after start.')

    def __str__(self):
        return f"{self.name} ({self.start_datetime.strftime('%d %b %H:%M')} → {self.end_datetime.strftime('%d %b %H:%M')})"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ShiftAssignment(models.Model):
    """ Links a specific User (staff member) to a Shift. """
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shift_assignments')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['shift', 'user']
        ordering = ['shift__start_datetime', 'user__first_name']

    def __str__(self):
        return f"{self.user.get_full_name()} assigned to {self.shift}"

# schedule/models.py  (append at bottom)


class SwapRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    requester      = models.ForeignKey(User, related_name='sent_swaps',   on_delete=models.CASCADE)
    shift          = models.ForeignKey(Shift, on_delete=models.CASCADE)   # shift the requester wants to give away
    desired_shift  = models.ForeignKey(Shift, related_name='desired_swaps', null=True, blank=True, on_delete=models.CASCADE)
    responder      = models.ForeignKey(User, related_name='received_swaps', null=True, blank=True, on_delete=models.CASCADE,
                                       help_text="User who should take the shift (optional)")
    status         = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at     = models.DateTimeField(auto_now_add=True)
    reviewed_by    = models.ForeignKey(User, related_name='reviewed_swaps', null=True, blank=True, on_delete=models.SET_NULL)
    notes          = models.TextField(blank=True)

    class Meta:
        unique_together = ('requester', 'shift', 'status')   # only one pending per shift

    def __str__(self):
        return f"{self.requester} → {self.shift} ({self.status})"


class ShiftStockTake(models.Model):
    SECTION_CHOICES = (
        ('Bar',     'Bar'),
    )
    shift   = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='stock_takes')
    item    = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    section = models.CharField(max_length=10, choices=SECTION_CHOICES)

    opening_physical = models.DecimalField(max_digits=10, decimal_places=3)
    closing_physical = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    opening_system   = models.DecimalField(max_digits=10, decimal_places=3)
    closing_system   = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    @property
    def opening_disparity(self):
        return self.opening_physical - self.opening_system

    @property
    def closing_disparity(self):
        if self.closing_physical is None or self.closing_system is None:
            return None
        return self.closing_physical - self.closing_system

    class Meta:
        unique_together = ('shift', 'item', 'section')


