from django.contrib.admin.apps import AdminConfig


class SuperuserAdminConfig(AdminConfig):
    """Makes Django use our superuser-only admin site instead of the default one."""

    default_site = "config.admin_site.SuperuserAdminSite"