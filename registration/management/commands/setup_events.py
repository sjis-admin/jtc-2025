# registration/management/commands/setup_events.py
from django.core.management.base import BaseCommand
from registration.models import Event

class Command(BaseCommand):
    help = 'Set up default events for Josephite Tech Carnival 2025'
    
    def handle(self, *args, **options):
        events_data = [
            {
                'name': 'Web Development Competition',
                'description': 'Create a responsive website using HTML, CSS, and JavaScript within the given time limit.',
                'fee': 500.00
            },
            {
                'name': 'Programming Contest',
                'description': 'Solve algorithmic problems using your preferred programming language.',
                'fee': 500.00
            },
            {
                'name': 'Database Design Challenge',
                'description': 'Design and implement a database solution for a real-world scenario.',
                'fee': 500.00
            },
            {
                'name': 'Mobile App Development',
                'description': 'Develop a mobile application prototype addressing a specific problem.',
                'fee': 500.00
            },
            {
                'name': 'Cybersecurity Quiz',
                'description': 'Test your knowledge of cybersecurity concepts and best practices.',
                'fee': 500.00
            },
            {
                'name': 'AI/ML Project Showcase',
                'description': 'Present your machine learning or AI project to a panel of judges.',
                'fee': 500.00
            },
            {
                'name': 'Tech Quiz Competition',
                'description': 'General technology quiz covering various domains of computer science.',
                'fee': 500.00
            },
            {
                'name': 'Game Development Challenge',
                'description': 'Create a simple game using any game development framework or engine.',
                'fee': 500.00
            },
        ]
        
        created_count = 0
        for event_data in events_data:
            event, created = Event.objects.get_or_create(
                name=event_data['name'],
                defaults={
                    'description': event_data['description'],
                    'fee': event_data['fee'],
                    'is_active': True
                }
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created event: {event.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Event already exists: {event.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} new events.')
        )
