from django.core.management.base import BaseCommand

from accounts.models import StaffUser
from bookings.models import Service
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Seed demo tenant, staff users, and services."

    def handle(self, *args, **options):
        tenant, created = Tenant.objects.get_or_create(
            business_name="Demo Clinic",
            defaults={
                "vertical": "doctor",
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS("Created Demo Clinic tenant."))
        else:
            self.stdout.write("Demo Clinic tenant already exists.")

        platform_admin, created = StaffUser.objects.get_or_create(
            username="demo_platform_admin",
            defaults={
                "role": StaffUser.Role.PLATFORM_ADMIN,
            },
        )

        if created:
            platform_admin.set_password("demo-password-123")
            platform_admin.save()
            self.stdout.write(self.style.SUCCESS("Created demo platform admin."))
        else:
            self.stdout.write("Demo platform admin already exists.")

        owner, created = StaffUser.objects.get_or_create(
            username="demo_owner",
            defaults={
                "tenant": tenant,
                "role": StaffUser.Role.OWNER,
            },
        )

        if created:
            owner.set_password("demo-password-123")
            owner.save()
            self.stdout.write(self.style.SUCCESS("Created demo clinic owner."))
        else:
            self.stdout.write("Demo clinic owner already exists.")

        services = [
            ("General Consultation", 30),
            ("Follow-up Consultation", 20),
            ("Extended Consultation", 60),
        ]

        for name, duration_minutes in services:
            service, created = Service.objects.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "duration_minutes": duration_minutes,
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created service: {service.name}.")
                )
            else:
                self.stdout.write(f"Service already exists: {service.name}.")
