
from django.core.management.base import BaseCommand
from registration.models import Student, Team, TeamMember, StudentEventRegistration

class Command(BaseCommand):
    help = 'Inspects team data for a given student'

    def add_arguments(self, parser):
        parser.add_argument('student_identifier', type=str, help='The ID or registration_id of the student to inspect')

    def handle(self, *args, **options):
        student_identifier = options['student_identifier']
        try:
            if student_identifier.isdigit():
                student = Student.objects.get(id=int(student_identifier))
            else:
                student = Student.objects.get(registration_id=student_identifier)
        except Student.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Student with identifier \'{student_identifier}\' not found.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Inspecting team data for student: {student.name} ({student.id})'))

        registrations = StudentEventRegistration.objects.filter(student=student, team__isnull=False)
        if not registrations.exists():
            self.stdout.write('This student is not registered for any team events.')
            return

        for reg in registrations:
            team = reg.team
            self.stdout.write(self.style.WARNING(f'  Event: {reg.event.name}, Team: {team.name} ({team.id})'))
            
            members = team.members.all()
            if not members.exists():
                self.stdout.write('    No team members found for this team.')
            else:
                for member in members:
                    self.stdout.write(f'    - Member: {member.name} (Leader: {member.is_leader})')
