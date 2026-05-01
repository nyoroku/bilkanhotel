import logging
logger = logging.getLogger(__name__)

# pos/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy, reverse
from django.db.models import Prefetch
from .models import Schedule, Shift, ShiftAssignment, SwapRequest
from .forms import ScheduleForm, ShiftForm, ShiftAssignmentForm
from django.views.generic import UpdateView, DeleteView
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from accounts.models import User
from django.http import JsonResponse, Http404
from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from pos.models import Sale, OrderItem
from django.db.models import Sum
from datetime import date, timedelta
from django.utils import timezone


# from .decorators import admin_manager_required

# We use class-based views for a clean structure

# @admin_manager_required
class ScheduleListView(LoginRequiredMixin, ListView):
    """ Displays a list of all schedules. """
    model = Schedule
    template_name = 'schedule/schedule_list.html'
    context_object_name = 'schedules'
    paginate_by = 10


# @admin_manager_required
class ScheduleCreateView(LoginRequiredMixin, CreateView):
    """ Handles the creation of a new schedule. """
    model = Schedule
    form_class = ScheduleForm
    template_name = 'schedule/schedule_form.html'
    success_url = reverse_lazy('schedule:schedule_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Create New Schedule'
        return context

    def form_valid(self, form):
        messages.success(self.request, "Schedule created successfully.")
        return super().form_valid(form)


class ScheduleDetailView(LoginRequiredMixin, DetailView):
    model = Schedule
    template_name = 'schedule/schedule_detail.html'
    context_object_name = 'schedule'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        schedule = self.get_object()

        # Ensure we always get shifts WITH their assignments/users pre-fetched
        shifts = (schedule.shifts
                  .prefetch_related(
                      Prefetch('assignments',
                               queryset=ShiftAssignment.objects.select_related('user'))
                  )
                  .order_by('start_datetime'))
        context['shifts'] = shifts

        # Users already assigned to ANY shift in this schedule
        assigned_user_ids = (ShiftAssignment.objects
                             .filter(shift__schedule=schedule)
                             .values_list('user_id', flat=True)
                             .distinct())

        context['assigned_users'] = (User.objects
                                     .filter(id__in=assigned_user_ids, is_active=True)
                                     .order_by('first_name'))

        context['shift_form'] = ShiftForm(initial={'schedule': schedule})
        context['assignment_form'] = ShiftAssignmentForm()

        return context


class ShiftCreateView(LoginRequiredMixin, CreateView):
    """ Create a new shift inside a given schedule with AJAX support. """
    model = Shift
    form_class = ShiftForm

    def form_valid(self, form):
        schedule = get_object_or_404(Schedule, pk=self.kwargs['schedule_pk'])
        form.instance.schedule = schedule

        response = super().form_valid(form)

        # Handle AJAX requests
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            messages.success(self.request, "Shift created successfully.")
            return JsonResponse({
                'success': True,
                'message': 'Shift created successfully.',
                'shift_id': self.object.pk
            })

        messages.success(self.request, "Shift created successfully.")
        return response

    def form_invalid(self, form):
        # Handle AJAX requests
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'errors': form.errors
            })

        # Fallback for non-AJAX requests - display specific errors
        error_messages = []
        for field, errors in form.errors.items():
            field_name = form[field].label if hasattr(form[field], 'label') else field
            for error in errors:
                error_messages.append(f"{field_name}: {error}")

        if error_messages:
            messages.error(self.request, "Please correct the following errors: " + "; ".join(error_messages))
        else:
            messages.error(self.request, 'Please correct the errors in the form.')

        return redirect('schedule:schedule_detail', pk=self.kwargs['schedule_pk'])

    def get_success_url(self):
        return reverse('schedule:schedule_detail',
                       kwargs={'pk': self.kwargs['schedule_pk']})


class ShiftAssignmentCreateView(LoginRequiredMixin, CreateView):
    model = ShiftAssignment
    form_class = ShiftAssignmentForm

    # ---------- helpers ----------
    def _get_shift(self):
        # 1. try URL kwarg first (/shifts/123/assign/)
        shift_pk = self.kwargs.get('shift_pk')

        # 2. fallback to POST body (form field called 'shift')
        if not shift_pk and self.request.method == 'POST':
            shift_pk = self.request.POST.get('shift')

        # 3. fallback to GET parameters (for AJAX requests)
        if not shift_pk and self.request.method == 'GET':
            shift_pk = self.request.GET.get('shift')

        if not shift_pk:
            raise Http404("No shift specified")

        return get_object_or_404(Shift, pk=shift_pk)

    # ---------- form handling ----------
    def get_form(self, form_class=None):
        """Override to inject the filtered user queryset."""
        form = super().get_form(form_class)
        shift = self._get_shift()
        already_assigned = shift.assignments.values_list('user_id', flat=True)
        form.fields['user'].queryset = (
            form.fields['user']
            .queryset.filter(is_active=True)
            .exclude(id__in=already_assigned)
            .order_by('first_name', 'last_name')
        )
        form.instance.shift = shift  # link the FK early
        return form

    # ---------- enhanced multi-user assignment handling ----------
    def post(self, request, *args, **kwargs):
        """Handle both single and multiple user assignments."""
        try:
            shift = self._get_shift()
        except (Http404, Exception) as e:
            logger.error(f"Error getting shift: {e}")
            error_msg = "Invalid shift specified."
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(self.request, error_msg)
            return redirect('schedule:schedule_list')

        # Check if this is a multi-user assignment (from the enhanced UI)
        user_ids = request.POST.getlist('users')  # Multiple users from checkboxes
        single_user_id = request.POST.get('user')  # Single user from original form
        notes = request.POST.get('notes', '')

        if user_ids:
            # Handle multiple user assignment
            return self._handle_multi_user_assignment(shift, user_ids, notes)
        elif single_user_id:
            # Handle single user assignment (fallback to original behavior)
            return self._handle_single_user_assignment(shift, single_user_id, notes)
        else:
            # No users specified
            return self._redirect_to_schedule(shift)

    def _handle_multi_user_assignment(self, shift, user_ids, notes):
        """Handle assignment of multiple users to a shift."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        success_count = 0
        error_messages = []
        assigned_users = []

        # Get already assigned users to prevent duplicates
        already_assigned = set(shift.assignments.values_list('user_id', flat=True))

        for user_id in user_ids:
            try:
                # Validate user exists and is active
                user = User.objects.get(id=user_id, is_active=True)

                # Check if user is already assigned
                if user.id in already_assigned:
                    error_messages.append(f"{user.get_full_name()} is already assigned to this shift.")
                    continue

                # Create the assignment
                assignment = ShiftAssignment.objects.create(
                    shift=shift,
                    user=user,
                    notes=notes
                )
                assigned_users.append(user.get_full_name())
                already_assigned.add(user.id)  # Prevent duplicate assignments in same batch
                success_count += 1

            except User.DoesNotExist:
                error_messages.append(f"User with ID {user_id} not found or inactive.")
            except Exception as e:
                logger.error(f"Error assigning user {user_id} to shift {shift.id}: {e}")
                error_messages.append(f"Failed to assign user {user_id}: {str(e)}")

        # Prepare response messages
        success_msg = ""
        if success_count > 0:
            user_list = ", ".join(assigned_users)
            success_msg = f"Successfully assigned {success_count} staff member{'s' if success_count > 1 else ''} ({user_list}) to {shift.name}."

        error_msg = ""
        if error_messages:
            error_msg = " | ".join(error_messages)

        # Return appropriate response
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response_data = {
                'success': success_count > 0,
                'message': success_msg,
                'success_count': success_count,
                'assigned_users': assigned_users
            }
            if error_messages:
                response_data['errors'] = error_messages
                response_data['error_message'] = error_msg

            status_code = 200 if success_count > 0 else 400
            return JsonResponse(response_data, status=status_code)
        else:
            # Non-AJAX request
            if success_msg:
                messages.success(self.request, success_msg)
            if error_msg:
                messages.error(self.request, error_msg)
            return self._redirect_to_schedule(shift)

    def _handle_single_user_assignment(self, shift, user_id, notes):
        """Handle assignment of a single user to a shift (original behavior)."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(id=user_id, is_active=True)

            # Check for existing assignment
            if ShiftAssignment.objects.filter(shift=shift, user=user).exists():
                msg = f"{user.get_full_name()} is already assigned to this shift."
                if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': msg}, status=400)
                messages.error(self.request, msg)
                return self._redirect_to_schedule(shift)

            # Create assignment
            assignment = ShiftAssignment.objects.create(
                shift=shift,
                user=user,
                notes=notes
            )

            msg = f"Successfully assigned {user.get_full_name()} to {shift.name}."
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': msg})
            messages.success(self.request, msg)
            return self._redirect_to_schedule(shift)

        except User.DoesNotExist:
            msg = "Selected user not found or inactive."
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=400)
            messages.error(self.request, msg)
            return self._redirect_to_schedule(shift)
        except Exception as e:
            logger.error(f"Error in single user assignment: {e}")
            msg = f"Failed to assign user: {str(e)}"
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=500)
            messages.error(self.request, msg)
            return self._redirect_to_schedule(shift)

    # ---------- original methods (kept for backward compatibility) ----------
    def form_valid(self, form):
        """Legacy form handling - kept for backward compatibility."""
        # Prevent race-condition double click
        if ShiftAssignment.objects.filter(
                shift=form.instance.shift,
                user=form.cleaned_data['user']
        ).exists():
            msg = f"{form.cleaned_data['user'].get_full_name()} is already assigned to this shift."
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=400)
            messages.error(self.request, msg)
            return self._redirect_to_schedule(form.instance.shift)

        self.object = form.save()
        msg = f"Assigned {self.object.user.get_full_name()} to shift."
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})
        messages.success(self.request, msg)
        return self._redirect_to_schedule(form.instance.shift)

    def form_invalid(self, form):
        """Legacy form error handling - kept for backward compatibility."""
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(self.request, f"{field}: {err}")
        try:
            shift = self._get_shift()
            return self._redirect_to_schedule(shift)
        except:
            return redirect('schedule:schedule_list')

    # ---------- helpers ----------
    def _redirect_to_schedule(self, shift):
        """Helper to redirect back to schedule detail page."""
        try:
            return redirect(reverse('schedule:schedule_detail', kwargs={'pk': shift.schedule_id}))
        except Exception as e:
            logger.error(f"Error redirecting to schedule: {e}")
            return redirect('schedule:schedule_list')

class ScheduleUpdateView(LoginRequiredMixin, UpdateView):
    model = Schedule
    form_class = ScheduleForm
    template_name = 'schedule/schedule_form.html'
    success_url = reverse_lazy('schedule:schedule_list')


class ScheduleDeleteView(LoginRequiredMixin, DeleteView):
    model = Schedule
    template_name = 'schedule/confirm_delete.html'
    success_url = reverse_lazy('schedule:schedule_list')


# ---------- Update / Delete Shift ----------


class ShiftUpdateView(LoginRequiredMixin, UpdateView):
    model = Shift
    form_class = ShiftForm
    template_name = 'schedule/shift_form.html'

    def get_success_url(self):
        return reverse('schedule:schedule_detail', args=[self.object.schedule.pk])


class ShiftDeleteView(LoginRequiredMixin, DeleteView):
    model = Shift
    template_name = 'schedule/confirm_delete.html'

    def get_success_url(self):
        return reverse('schedule:schedule_detail', args=[self.object.schedule.pk])


# ---------- Delete Assignment ----------
class ShiftAssignmentDeleteView(LoginRequiredMixin, DeleteView):
    model = ShiftAssignment
    template_name = 'schedule/confirm_delete.html'

    def get_object(self, queryset=None):
        return get_object_or_404(
            ShiftAssignment,
            shift_id=self.kwargs['pk'],  # int
            user_id=self.kwargs['user_id']  # UUID
        )

    def get_success_url(self):
        return reverse('schedule:schedule_detail',
                       args=[self.object.shift.schedule.pk])


# ---------- AJAX endpoint to get available users for shift assignment ----------
@login_required
def get_available_users_for_shift(request, shift_id):
    """AJAX endpoint to get users not assigned to a specific shift."""
    if request.method == 'GET':
        try:
            shift = get_object_or_404(Shift, pk=shift_id)

            # Get users not assigned to this shift
            assigned_user_ids = shift.assignments.values_list('user_id', flat=True)
            available_users = User.objects.filter(
                is_active=True
            ).exclude(id__in=assigned_user_ids).order_by('first_name', 'last_name')

            users_data = [
                {
                    'id': str(user.id),
                    'name': user.get_full_name(),
                    'email': user.email
                }
                for user in available_users
            ]

            return JsonResponse({'users': users_data})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ---------- AJAX endpoint to get swappable users for a shift ----------
@login_required
def get_swappable_users_for_shift(request, shift_id):
    """AJAX endpoint to get users assigned to other shifts (for swapping)."""
    if request.method == 'GET':
        try:
            shift = get_object_or_404(Shift, pk=shift_id)

            # Get users assigned to other shifts in the same schedule
            current_shift_user_ids = shift.assignments.values_list('user_id', flat=True)

            other_assignments = ShiftAssignment.objects.filter(
                shift__schedule=shift.schedule
            ).exclude(
                shift=shift
            ).select_related('user', 'shift')

            swappable_data = []
            for assignment in other_assignments:
                swappable_data.append({
                    'user_id': str(assignment.user.id),
                    'user_name': assignment.user.get_full_name(),
                    'shift_id': assignment.shift.id,
                    'shift_name': f"{assignment.shift.name} - {assignment.shift.date} {assignment.shift.start_time}"
                })

            return JsonResponse({'swappable': swappable_data})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ---------- Swap two users between two shifts ----------

@require_POST
@login_required
@transaction.atomic
def swap_shift_assignments(request):
    try:
        from_shift = get_object_or_404(Shift, pk=request.POST['from_shift'])
        to_shift   = get_object_or_404(Shift, pk=request.POST['to_shift'])
        from_user  = get_object_or_404(User,  pk=request.POST['from_user'])
        to_user    = get_object_or_404(User,  pk=request.POST['to_user'])
    except KeyError:
        messages.error(request, "Missing required data.")
        return redirect("schedule:schedule_detail", pk=from_shift.schedule.pk)

    if from_shift == to_shift:
        messages.error(request, "Cannot swap within the same shift.")
        return redirect("schedule:schedule_detail", pk=from_shift.schedule.pk)

    # 1. Fetch the two rows we are going to swap
    from_assign = get_object_or_404(ShiftAssignment, shift=from_shift, user=from_user)
    to_assign   = get_object_or_404(ShiftAssignment, shift=to_shift,   user=to_user)

    # 2. Make sure the “new” combinations do not already exist
    if ShiftAssignment.objects.filter(shift=to_shift, user=from_user).exists():
        messages.error(request, f"{from_user.get_full_name()} is already assigned to the target shift.")
        return redirect("schedule:schedule_detail", pk=from_shift.schedule.pk)
    if ShiftAssignment.objects.filter(shift=from_shift, user=to_user).exists():
        messages.error(request, f"{to_user.get_full_name()} is already assigned to the target shift.")
        return redirect("schedule:schedule_detail", pk=from_shift.schedule.pk)

    # 3. Save notes before deleting
    from_notes = from_assign.notes
    to_notes   = to_assign.notes

    # 4. Delete the old rows
    from_assign.delete()
    to_assign.delete()

    # 5. Re-create rows with swapped shifts
    ShiftAssignment.objects.create(shift=to_shift,   user=from_user, notes=from_notes)
    ShiftAssignment.objects.create(shift=from_shift, user=to_user,   notes=to_notes)

    messages.success(request, f"Swapped {from_user.get_full_name()} ↔ {to_user.get_full_name()}.")
    return redirect("schedule:schedule_detail", pk=from_shift.schedule.pk)


class MyScheduleView(LoginRequiredMixin, TemplateView):
    template_name = 'schedule/my_schedule.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()

        # Day - shifts that start on today
        day_shifts = (user.shift_assignments
                      .filter(shift__start_datetime__date=today)
                      .select_related('shift__schedule')
                      .order_by('shift__start_datetime'))

        # Week
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        week_shifts = (user.shift_assignments
                       .filter(shift__start_datetime__date__range=[week_start, week_end])
                       .select_related('shift__schedule')
                       .order_by('shift__start_datetime'))

        # Month
        month_start = today.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        month_shifts = (user.shift_assignments
                        .filter(shift__start_datetime__date__gte=month_start,
                                shift__start_datetime__date__lt=next_month)
                        .select_related('shift__schedule')
                        .order_by('shift__start_datetime'))

        ctx.update({
            'day_shifts': day_shifts,
            'week_shifts': week_shifts,
            'month_shifts': month_shifts,
            'today': today,
            'week_start': week_start,
            'week_end': week_end,
            'month_start': month_start,
        })
        return ctx


@login_required
def create_swap_request(request, pk):
    assignment = get_object_or_404(request.user.shift_assignments, shift_id=pk)
    if SwapRequest.objects.filter(requester=request.user, shift=assignment.shift, status='pending').exists():
        messages.warning(request, "You already have a pending swap for this shift.")
        return redirect('schedule:my_schedule')

    SwapRequest.objects.create(
        requester=request.user,
        shift=assignment.shift,
        notes=request.POST.get('notes', '')
    )
    messages.success(request, "Swap request sent to manager.")
    return redirect('schedule:my_schedule')


@method_decorator(staff_member_required, name='dispatch')
class SwapRequestListView(LoginRequiredMixin, ListView):
    model = SwapRequest
    template_name = 'schedule/swap_request_list.html'
    context_object_name = 'requests'
    ordering = ['-created_at']
    paginate_by = 20


@staff_member_required
@transaction.atomic
def approve_swap(request, pk):
    swap = get_object_or_404(SwapRequest, pk=pk, status='pending')
    # Move assignment to the desired shift (or leave empty)
    ShiftAssignment.objects.filter(shift=swap.shift, user=swap.requester).update(shift=swap.desired_shift or swap.shift)
    swap.status = 'approved'
    swap.reviewed_by = request.user
    swap.save(update_fields=['status', 'reviewed_by'])
    messages.success(request, "Swap approved.")
    return redirect('schedule:swap_request_list')


@staff_member_required
@transaction.atomic
def reject_swap(request, pk):
    swap = get_object_or_404(SwapRequest, pk=pk, status='pending')
    swap.status = 'rejected'
    swap.reviewed_by = request.user
    swap.save(update_fields=['status', 'reviewed_by'])
    messages.info(request, "Swap rejected.")
    return redirect('schedule:swap_request_list')


@login_required
def shift_sales_summary_view(request):
    """
    Displays a detailed sales summary for the current user's active shift,
    broken down by section (Kitchen/Bar) and payment method.
    """
    now = timezone.localtime()

    # 1. Find the user's currently active shift assignment
    active_assignment = ShiftAssignment.objects.filter(
        user=request.user,
        shift__start_datetime__lte=now,
        shift__end_datetime__gte=now
    ).select_related('shift').first()

    if not active_assignment:
        # If the user is not in an active shift, show a message
        return render(request, 'schedule/no_shift.html')

    # 2. Get all sales recorded during this specific shift assignment
    sales_in_shift = Sale.objects.filter(assignment=active_assignment)

    # 3. Perform a powerful query to get the sales breakdown
    sales_breakdown = sales_in_shift.values(
        'payment_method',
        'orders__items__menu_item__category__module'  # Group by the section (Kitchen/Bar)
    ).annotate(
        total=Sum('amount_paid')
    ).order_by('orders__items__menu_item__category__module', 'payment_method')

    # 4. Process the query results into a structured format for the template
    summary_data = {
        'Bar': {'Cash': 0, 'Mpesa': 0, 'Credit': 0, 'total': 0},
        'grand_total': 0
    }

    for item in sales_breakdown:
        section = item['orders__items__menu_item__category__module']
        payment_method = item['payment_method']
        total = item['total'] or 0

        if section in summary_data and payment_method in summary_data[section]:
            summary_data[section][payment_method] += total
            summary_data[section]['total'] += total
            summary_data['grand_total'] += total

    context = {
        'shift': active_assignment.shift,
        'summary_data': summary_data,
    }
    return render(request, 'schedule/shift_sales_summary.html', context)


@login_required
def section_shift_summary_view(request, section):
    """
    Displays a sales summary for the entire section's currently active shift.
    """
    now = timezone.localtime()

    # 1. Map the URL section to the corresponding User role
    role_map = {
        'bar': 'bar_staff',
    }

    target_role = role_map.get(section)
    if not target_role:
        return render(request, 'schedule/no_shift.html', {
            'message': f"Invalid section specified: {section}"
        })

    # 2. Find the currently active shift assignment for ANY user with the target role
    active_assignment = ShiftAssignment.objects.filter(
        user__role=target_role,
        shift__start_datetime__lte=now,
        shift__end_datetime__gte=now,
    ).select_related('shift', 'user').first()

    if not active_assignment:
        return render(request, 'schedule/no_shift.html', {
            'message': f"No active shift for {section.capitalize()} station"
        })

    shift = active_assignment.shift

    # 3. Filter sales based on timestamp and the section of items
    section_name_for_filter = section.capitalize()

    # 4. Get sales breakdown by payment method with proper distinct handling
    # First get the unique sale IDs to avoid counting duplicates from JOIN
    unique_sale_ids = Sale.objects.filter(
        processed_at__range=(shift.start_datetime, shift.end_datetime),
        order__items__menu_item__category__module=section_name_for_filter
    ).distinct().values_list('id', flat=True)

    # Then aggregate only those unique sales
    sales_breakdown = Sale.objects.filter(
        id__in=unique_sale_ids
    ).values('payment_method').annotate(
        total=Sum('amount_paid')
    ).order_by('payment_method')

    # 5. Process the results into summary data
    summary_data = {
        'Cash': 0,
        'Mpesa': 0,
        'Credit': 0,
        'grand_total': 0
    }

    for item in sales_breakdown:
        payment_method = item['payment_method']
        total = item['total'] or 0
        if payment_method in summary_data:
            summary_data[payment_method] += total
        summary_data['grand_total'] += total

    context = {
        'shift': shift,
        'assignment': active_assignment,
        'summary_data': summary_data,
        'section_name': section.capitalize(),
    }

    return render(request, 'schedule/shift_sales_summary.html', context)


@login_required
@staff_member_required
def shift_handover_summary(request, shift_id):
    """
    Detailed summary of a shift for handover from one team/manager to another.
    Shows sales, expected cash, and stock disparities.
    """
    shift = get_object_or_404(Shift, pk=shift_id)
    
    # Financial Summary
    sales = Sale.objects.filter(
        processed_at__gte=shift.start_datetime,
        processed_at__lte=shift.end_datetime
    )
    
    total_sales = sales.aggregate(total=Sum('amount_paid'))['total'] or 0
    payment_breakdown = sales.values('payment_method').annotate(total=Sum('amount_paid'))
    
    # Waiter Cash Drops
    waiter_drops = sales.filter(payment_method=Sale.PaymentMethod.CASH).values(
        'order__waiter__first_name', 
        'order__waiter__last_name',
        'order__waiter__username'
    ).annotate(total_cash=Sum('amount_paid')).order_by('order__waiter__first_name')

    # Stock Take Summary
    stock_takes = shift.stock_takes.select_related('item').all()
    
    # Unresolved Orders during this shift
    unresolved_orders = Order.objects.filter(
        created_at__gte=shift.start_datetime,
        created_at__lte=shift.end_datetime,
        status__in=[Order.Status.PENDING, Order.Status.PREPARING, Order.Status.READY]
    ).select_related('table', 'waiter')

    context = {
        'shift': shift,
        'total_sales': total_sales,
        'payment_breakdown': payment_breakdown,
        'waiter_drops': waiter_drops,
        'stock_takes': stock_takes,
        'unresolved_orders': unresolved_orders,
        'now': timezone.now(),
    }
    
    return render(request, 'schedule/handover_summary.html', context)

