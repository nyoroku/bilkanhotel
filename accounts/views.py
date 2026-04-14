import json
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import User  # Assuming User is in the same app, otherwise from accounts.models
from .forms import UserAdminCreationForm, UserAdminChangeForm  # Assuming these forms exist



def pin_login_view(request):
    """
    Displays the main PIN login screen with profiles for all operational staff
    (Waiters, Kitchen Staff, and Bar Staff).
    """
    # FIX: The query now includes all three roles.
    operational_staff = User.objects.filter(
        role__in=['waiter', 'kitchen_staff', 'bar_staff', 'butcher', 'cashier'],
        is_active=True
    ).order_by('role', 'first_name')

    return render(request, 'accounts/pin_login.html', {'staff_members': operational_staff})


# --- This view now handles role-based redirects ---

def process_pin_login(request):
    """
    Handles the PIN submission, authenticates the user, and redirects them
    to the correct dashboard based on their role.
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        user_id = data.get('userId')
        pin = data.get('pin')

        try:
            user = User.objects.get(id=user_id)
            if user.check_pin(pin):
                # PIN is correct. Log the user in.
                login(request, user)

                # --- FIX: Role-based redirect logic ---
                if user.role == 'waiter':
                    redirect_url = reverse('pos:waiter_dashboard')

                elif user.role == 'butcher':
                    redirect_url = reverse('pos:butchery_section')
                elif user.role == 'cashier':
                    redirect_url = reverse('pos:cashier_dashboard')
                elif user.role == 'kitchen_staff':
                    redirect_url = reverse('pos:unified_station_view', kwargs={'section': 'kitchen'})
                elif user.role == 'bar_staff':
                    redirect_url = reverse('pos:unified_station_view', kwargs={'section': 'bar'})
                else:
                    # A safe fallback to the main dashboard
                    redirect_url = reverse('pos:pos')

                return JsonResponse({'success': True, 'redirect_url': redirect_url})
            else:
                # PIN is incorrect
                return JsonResponse({'success': False, 'message': 'Invalid PIN'}, status=401)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'User not found'}, status=404)

    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


def user_logout_view(request):
    """Logs the user out and redirects to the PIN login screen."""
    logout(request)
    return redirect('accounts:pin_login')


@login_required
def staff_list_view(request):
    """
    Displays a paginated and searchable list of all staff members.
    """
    queryset = User.objects.all().order_by('first_name', 'last_name')

    # Search functionality
    search_query = request.GET.get('q', '')
    if search_query:
        queryset = queryset.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(role__icontains=search_query)
        )

    paginator = Paginator(queryset, 15)  # Show 15 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'accounts/staff_list.html', context)


@login_required
def staff_add_view(request):
    """
    Handles the creation of a new staff member using the custom form.
    """
    if request.method == 'POST':
        form = UserAdminCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Successfully created staff account for {user.get_full_name()}.")
            return redirect('accounts:staff_list')  # Assuming URL name is 'staff_list'
    else:
        form = UserAdminCreationForm()

    context = {
        'form': form,
        'form_title': 'Add New Staff Member'
    }
    return render(request, 'accounts/staff_form.html', context)


@login_required
def staff_edit_view(request, pk):
    """
    Handles editing an existing staff member's details and PIN.
    """
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserAdminChangeForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Successfully updated profile for {user.get_full_name()}.")
            return redirect('accounts:staff_list')
    else:
        form = UserAdminChangeForm(instance=user)

    context = {
        'form': form,
        'form_title': f'Edit Profile: {user.get_full_name()}',
        'user_to_edit': user
    }
    return render(request, 'accounts/staff_form.html', context)


@login_required
def staff_delete_view(request, pk):
    """
    Handles deleting a staff member after a confirmation prompt.
    """
    user_to_delete = get_object_or_404(User, pk=pk)

    if user_to_delete == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('pos:staff_list')

    if request.method == 'POST':
        user_name = user_to_delete.get_full_name()
        user_to_delete.delete()
        messages.success(request, f"Successfully deleted staff account for {user_name}.")
        return redirect('accounts:staff_list')

    context = {
        'item_to_delete': user_to_delete,
        'item_type': 'Staff Member'
    }
    return render(request, 'accounts/confirm_delete.html', context)