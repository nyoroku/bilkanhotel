from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from schedule.models import Schedule, Shift
from datetime import timedelta

class ScheduleViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='password123',
            first_name='Admin',
            last_name='Test'
        )
        self.client.login(email='admin@test.com', password='password123')
        
        self.schedule = Schedule.objects.create(
            name="Test Schedule",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=7),
            is_published=True
        )
        
        self.shift = Shift.objects.create(
            schedule=self.schedule,
            name="Morning Shift",
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(hours=8)
        )

    def test_shift_handover_summary_view(self):
        """Test that the handover summary loads without the PREPARING AttributeError."""
        url = reverse('schedule:shift_handover_summary', args=[self.shift.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_available_users_for_shift_ajax(self):
        """Test the AJAX endpoint used by the Assign Staff modal."""
        url = reverse('schedule:get_available_users', args=[self.shift.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('users', response.json())
