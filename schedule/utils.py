# pos/utils.py
from django.utils import timezone
from schedule.models import ShiftAssignment

def current_shift_for_user(user):
    """
    Returns the shift whose *datetime range* contains *now*.
    """
    now = timezone.now()
    assignment = (
        ShiftAssignment.objects
        .select_related('shift', 'shift__schedule')
        .filter(
            user=user,
            shift__start_datetime__lte=now,
            shift__end_datetime__gte=now,
            shift__schedule__status='Published'
        )
        .order_by('shift__start_datetime')
        .first()
    )
    return assignment.shift if assignment else None

