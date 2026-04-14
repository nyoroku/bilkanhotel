# pos/decorators.py

from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.decorators import user_passes_test


def admin_manager_required(view_func):
    """
    Decorator that checks if a user is logged in and has the role
    of 'admin' or 'manager'. If not, it adds an error message and
    redirects them to the homepage.
    """
    def check_role(user):
        if user.is_authenticated and user.role in ['admin', 'manager']:
            return True
        # If the check fails, we will handle the message and redirect
        # in the decorator logic itself.
        return False

    def wrapper(request, *args, **kwargs):
        if not check_role(request.user):
            messages.error(request, "You do not have the required permissions to access this page.")
            # Redirects to the main homepage for non-admins
            return redirect('pos:pos')
        return view_func(request, *args, **kwargs)

    return wrapper