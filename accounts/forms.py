from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.exceptions import ValidationError
from .models import User


class UserAdminCreationForm(forms.ModelForm):
    """
    Form for creating a brand-new user (password & PIN are required).
    """
    password        = forms.CharField(label='Password', widget=forms.PasswordInput)
    password_confirm = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)
    pin             = forms.CharField(
        label='4-Digit PIN',
        max_length=4,
        widget=forms.PasswordInput(attrs={'maxlength': 4})
    )
    pin_confirm = forms.CharField(
        label='Confirm PIN',
        max_length=4,
        widget=forms.PasswordInput(attrs={'maxlength': 4})
    )

    class Meta:
        model  = User
        fields = (
            'first_name', 'last_name', 'email', 'role',
            'phone_number', 'employee_id', 'basic_salary', 'waiter_reward_points', 'profile_image'
        )

    # ---------- validation ----------
    def clean_password_confirm(self):
        pw  = self.cleaned_data.get('password')
        pw2 = self.cleaned_data.get('password_confirm')
        if pw and pw2 and pw != pw2:
            raise ValidationError('Passwords do not match.')
        return pw2

    def clean_pin_confirm(self):
        pin  = self.cleaned_data.get('pin')
        pin2 = self.cleaned_data.get('pin_confirm')
        if pin and pin2 and pin != pin2:
            raise ValidationError('PINs do not match.')
        if pin and (not pin.isdigit() or len(pin) != 4):
            raise ValidationError('PIN must be exactly 4 digits.')
        return pin2

    def clean_profile_image(self):
        img = self.cleaned_data.get('profile_image')
        if img:
            if not img.content_type.startswith('image/'):
                raise ValidationError('Only image files are allowed.')
            if img.size > 2 * 1024 * 1024:
                raise ValidationError('Image file too large (max 2 MB).')
        return img

    # ---------- save ----------
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.set_pin(self.cleaned_data['pin'])
        if commit:
            user.save()
        return user


class UserAdminChangeForm(forms.ModelForm):
    """
    Form for editing existing users (password & PIN are optional).
    """
    password = ReadOnlyPasswordHashField(
        label='Password',
        help_text=(
            'Raw passwords are not stored; change the password using '
            '<a href="../password/">this form</a>.'
        ),
    )
    password_confirm = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput,
        required=False
    )
    pin = forms.CharField(
        label='New 4-Digit PIN',
        required=False,
        widget=forms.PasswordInput(attrs={'maxlength': 4, 'autocomplete': 'new-password'})
    )
    pin_confirm = forms.CharField(
        label='Confirm New PIN',
        required=False,
        widget=forms.PasswordInput(attrs={'maxlength': 4, 'autocomplete': 'new-password'})
    )

    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'email', 'role',
            'phone_number', 'employee_id', 'basic_salary', 'waiter_reward_points',
            'is_active', 'is_staff', 'profile_image'
        )

    # ---------- validation ----------
    def clean_profile_image(self):
        img = self.cleaned_data.get('profile_image')
        if img:
            if not img.content_type.startswith('image/'):
                raise ValidationError('Only image files are allowed.')
            if img.size > 2 * 1024 * 1024:
                raise ValidationError('Image file too large (max 2 MB).')
        return img

    def clean(self):
        cleaned_data = super().clean()

        # Password
        pw_confirm = cleaned_data.get('password_confirm')
        if pw_confirm:
            self.add_error(
                'password_confirm',
                'Use the separate password-change form instead.'
            )

        # PIN
        pin      = cleaned_data.get('pin')
        pin_conf = cleaned_data.get('pin_confirm')

        if pin or pin_conf:           # user touched at least one box
            if not (pin and pin_conf):
                self.add_error('pin_confirm', 'Both PIN boxes are required.')
            elif pin != pin_conf:
                self.add_error('pin_confirm', 'PINs do not match.')
            elif not pin.isdigit() or len(pin) != 4:
                self.add_error('pin', 'PIN must be exactly 4 digits.')

        return cleaned_data

    # ---------- save ----------
    def save(self, commit=True):
        user = super().save(commit=False)
        new_pin = self.cleaned_data.get('pin')
        if new_pin:
            user.set_pin(new_pin)
        if commit:
            user.save()
        return user