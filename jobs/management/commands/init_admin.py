import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Creates a default superuser if one does not already exist."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin", help="Admin username (default: admin)")
        parser.add_argument("--password", default=os.environ.get("DJANGO_ADMIN_PASSWORD", "admin123"), help="Admin password")
        parser.add_argument("--email", default="admin@rolepilot.local", help="Admin email")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        password = options["password"]
        email = options["email"]

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"Superuser '{username}' already exists."))
        else:
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created with password '{password}'."))
