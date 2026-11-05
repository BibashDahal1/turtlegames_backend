from django.contrib import admin


class SuperuserAdminSite(admin.AdminSite):
    """Only active superusers can log in to and use the admin."""

    site_header = "Turtle Games Admin"
    site_title = "Turtle Games"
    index_title = "Manage games and cards"

    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_superuser