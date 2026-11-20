from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

# Demo logins from the brief. One user per org.
SEED_USERS = [
    ("alice", "alice123", "ORG-A"),
    ("bob", "bob123", "ORG-B"),
]


class Command(BaseCommand):
    help = "Create (or reset) the demo users alice (ORG-A) and bob (ORG-B)."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        for username, password, org_id in SEED_USERS:
            # Idempotent: re-running resets the password and org.
            user, created = User.objects.get_or_create(username=username)
            user.org_id = org_id
            user.set_password(password)
            user.save()
            verb = "created" if created else "updated"
            self.stdout.write(f"{verb} {username} -> {org_id}")
