# core/admin.py
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.sites import UnfoldAdminSite

class MyAdminSite(UnfoldAdminSite):
    site_header = _("My Awesome Project")
    site_title  = _("My Project")
    index_title = _("Dashboard")

    def each_context(self, request):
        ctx = super().each_context(request)
        ctx["site_url"] = "https://myfrontend.com"   # any absolute URL you want
        ctx["site_name"] = _("Go to frontend")       # label of the link
        return ctx

admin_site = MyAdminSite(name="pos:pos")