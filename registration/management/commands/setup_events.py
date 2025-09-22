# registration/management/commands/setup_events.py
from django.core.management.base import BaseCommand
from registration.models import Event, Grade, EventOption
from decimal import Decimal

class Command(BaseCommand):
    help = 'Deletes all existing events and grades, then sets up default ones.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('--- Deleting ALL existing Events, Event Options, and Grades ---'))
        EventOption.objects.all().delete()
        Event.objects.all().delete()
        Grade.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('Successfully cleared old data.'))

        self.stdout.write(self.style.SUCCESS('--- Setting up Grades ---'))
        grades_data = [
            {'name': 'Grade 3', 'order': 3},
            {'name': 'Grade 4', 'order': 4},
            {'name': 'Grade 5', 'order': 5},
            {'name': 'Grade 6', 'order': 6},
            {'name': 'Grade 7', 'order': 7},
            {'name': 'Grade 8', 'order': 8},
            {'name': 'Grade 9', 'order': 9},
            {'name': 'Grade 10', 'order': 10},
            {'name': 'Grade 11', 'order': 11},
            {'name': 'Grade 12', 'order': 12},
        ]
        for grade_info in grades_data:
            grade, created = Grade.objects.update_or_create(
                name=grade_info['name'], 
                defaults={'order': grade_info['order']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created Grade: {grade.name}'))
        
        # Fetch grades for easy access
        grade3 = Grade.objects.get(order=3)
        grade4 = Grade.objects.get(order=4)
        grade5 = Grade.objects.get(order=5)
        grade6 = Grade.objects.get(order=6)
        grade7 = Grade.objects.get(order=7)
        grade8 = Grade.objects.get(order=8)
        grade9_12 = Grade.objects.filter(order__in=[9, 10, 11, 12])

        self.stdout.write(self.style.SUCCESS('--- Setting up Events and Event Options ---'))
        events_data = [
            {
                'name': 'Tech Quiz Competition',
                'description': 'General technology quiz covering various domains of computer science.',
                'target_grades': [grade3, grade4, grade5],
                'options': [
                    {'name': 'Individual', 'event_type': 'INDIVIDUAL', 'fee': '250.00'},
                ]
            },
            {
                'name': 'Web Development Competition',
                'description': 'Create a responsive website using HTML, CSS, and JavaScript.',
                'target_grades': grade9_12,
                'options': [
                    {'name': 'Team', 'event_type': 'TEAM', 'fee': '800.00', 'max_team_size': 3},
                ]
            },
            {
                'name': 'Programming Contest',
                'description': 'Solve algorithmic problems using your preferred programming language.',
                'target_grades': grade9_12,
                'options': [
                    {'name': 'Team', 'event_type': 'TEAM', 'fee': '1000.00', 'max_team_size': 3},
                ]
            },
            {
                'name': 'Game Development Challenge',
                'description': 'Create a simple game using any game development framework or engine.',
                'target_grades': [grade6, grade7, grade8],
                'options': [
                    {'name': 'Team', 'event_type': 'TEAM', 'fee': '700.00', 'max_team_size': 2},
                ]
            },
        ]
        
        created_count = 0
        for event_info in events_data:
            event, created = Event.objects.get_or_create(
                name=event_info['name'],
                defaults={'description': event_info['description'], 'is_active': True}
            )
            
            # Set target grades
            event.target_grades.set(event_info['target_grades'])

            # Create event options
            for option_info in event_info['options']:
                EventOption.objects.get_or_create(
                    event=event,
                    name=option_info['name'],
                    defaults={
                        'event_type': option_info['event_type'],
                        'fee': Decimal(option_info['fee']),
                        'max_team_size': option_info.get('max_team_size')
                    }
                )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created event: {event.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Event already exists: {event.name}, ensuring it is updated.'))
        
        self.stdout.write(self.style.SUCCESS(f'Successfully configured {len(events_data)} events.'))
