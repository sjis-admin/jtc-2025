
from django.core.management.base import BaseCommand
from registration.models import Student, TeamMember, StudentEventRegistration
from django.db.models import F

class Command(BaseCommand):
    help = 'Cleans up team data by removing students who were incorrectly added as team members.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting team data cleanup...'))

        # Find all team members whose name matches the name of the student who registered the team
        members_to_delete = TeamMember.objects.filter(
            team__studenteventregistration__student__name=F('name')
        )

        count = members_to_delete.count()

        if count == 0:
            self.stdout.write('No incorrect team members found to delete.')
            return

        self.stdout.write(f'Found {count} incorrect team members to delete.')

        # for member in members_to_delete:
        #     self.stdout.write(f'  - Deleting member: {member.name} from team: {member.team.name}')

        # Delete the incorrect team members
        members_to_delete.delete()

        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} incorrect team members.'))
