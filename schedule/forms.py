from django import forms
from django.core.exceptions import ValidationError
from datetime import datetime, time
from django.utils import timezone
from django.db.models import Q

from .models import Schedule, Shift, ShiftAssignment
from accounts.models import User


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ['name', 'start_date', 'end_date', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input'}),
            'start_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'select is-fullwidth'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end   = cleaned.get('end_date')
        if start and end and start >= end:
            raise ValidationError("End date must be after start date.")
        return cleaned


class ShiftForm(forms.ModelForm):   #  ⇦  already there
    start_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'input', 'type': 'datetime-local'})
    )
    end_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'input', 'type': 'datetime-local'})
    )

    class Meta:
        model = Shift          #  ⇦  this line must be present
        fields = ['schedule', 'name', 'start_datetime', 'end_datetime', 'notes']
        widgets = {
            'schedule': forms.Select(attrs={'class': 'select'}),
            'name': forms.TextInput(attrs={'class': 'input'}),
            'notes': forms.Textarea(attrs={'class': 'textarea', 'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_datetime')
        end = cleaned.get('end_datetime')
        schedule = cleaned.get('schedule')

        if start and end:
            if start >= end:
                raise ValidationError("End must be after start.")

            if schedule:
                tz = timezone.get_current_timezone()
                schedule_start = timezone.make_aware(
                    datetime.combine(schedule.start_date, time.min), tz
                )
                schedule_end = timezone.make_aware(
                    datetime.combine(schedule.end_date, time.max), tz
                )

                if start < schedule_start or end > schedule_end:
                    raise ValidationError(
                        f"Shift must be within the schedule period "
                        f"({schedule.start_date} – {schedule.end_date})."
                    )

        return cleaned

class ShiftAssignmentForm(forms.ModelForm):
    class Meta:
        model = ShiftAssignment
        fields = ['user', 'notes']
        widgets = {
            'user': forms.Select(attrs={'class': 'select'}),
            'notes': forms.Textarea(attrs={'class': 'textarea', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active users
        self.fields['user'].queryset = User.objects.filter(is_active=True)

    def clean_user(self):
        user = self.cleaned_data['user']
        shift = self.cleaned_data.get('shift')   # passed via view / form

        if not user or not shift:
            return user

        # Overlap detection
        overlaps = ShiftAssignment.objects.filter(
            user=user,
            shift__start_datetime__lt=shift.end_datetime,
            shift__end_datetime__gt=shift.start_datetime
        ).exclude(pk=self.instance.pk if self.instance else None)

        if overlaps.exists():
            raise ValidationError(
                f"{user.get_full_name()} is already assigned to an overlapping shift."
            )
        return user