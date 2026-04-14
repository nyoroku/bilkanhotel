"""
URL configuration for hotela project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.urls import reverse_lazy
from trucks.views import logistics_report_view

# ===================================================================
# --- 1. CUSTOMIZE THE ADMIN SITE ---
# ===================================================================

# This sets the main title in the admin header (e.g., "JuliFarm Administration")
admin.site.site_header = "JuliFarm Administration"

# This sets the title in the browser tab for the admin pages
admin.site.site_title = "JuliFarm Admin Portal"

# This sets the welcome text on the admin homepage
admin.site.index_title = "Welcome to the JuliFarm Manager Portal"

# --- 2. SET THE "VIEW SITE" URL ---
# This tells Django that the "View site" link should go to your main POS dashboard
admin.site.site_url = reverse_lazy('pos:pos')

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("core.urls")),
    path("", include("julifarm.urls")),
    path("", include("pos.urls")),
    path("", include("payroll.urls")),
    path("", include("schedule.urls")),
    path("", include("trucks.urls")),
    path("", include("accounts.urls")),
    path('select2/', include('django_select2.urls')),
    path('trucks/printable-report/', logistics_report_view, name='logistics_printable_report'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
