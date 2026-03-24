from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from workout_plans.services import import_garmin_workouts_for_user


class Command(BaseCommand):
    help = "Import user-created Garmin workouts into local database."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Django username to import workouts for")

    def handle(self, *args, **options):
        username = options["username"]
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as e:
            raise CommandError(f"User not found: {username}") from e

        result = import_garmin_workouts_for_user(user)
        if not result.get("ok"):
            raise CommandError(str(result))

        self.stdout.write(self.style.SUCCESS(str(result)))

