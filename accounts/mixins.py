from accounts.models import StaffUser


class TenantScopedMixin:
    tenant_lookup = "tenant"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if not user.is_authenticated:
            return queryset.none()

        if user.is_superuser or user.role == StaffUser.Role.PLATFORM_ADMIN:
            return queryset

        if not user.tenant_id:
            return queryset.none()

        return queryset.filter(**{self.tenant_lookup: user.tenant_id})
