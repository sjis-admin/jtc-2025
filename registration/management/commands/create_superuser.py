# registration/management/commands/create_superuser.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create a superuser for the application'
    
    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='admin', help='Username for superuser')
        parser.add_argument('--email', type=str, default='admin@josephitetechclub.com', help='Email for superuser')
        parser.add_argument('--password', type=str, default='admin123', help='Password for superuser')
    
    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'Superuser with username "{username}" already exists.')
            )
            return
        
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name='System',
            last_name='Administrator'
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Superuser "{username}" created successfully.')
        )
        self.stdout.write(f'Username: {username}')
        self.stdout.write(f'Email: {email}')
        self.stdout.write(f'Password: {password}')
        self.stdout.write(
            self.style.WARNING('Please change the password after first login!')
        )