# registration/management/commands/setup_admin_logs.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random

from registration.models import AdminLog, Student, Payment, Event

class Command(BaseCommand):
    help = 'Setup sample admin logs for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-sample',
            action='store_true',
            help='Create sample log entries for testing',
        )
        parser.add_argument(
            '--cleanup-old',
            action='store_true',
            help='Clean up logs older than 90 days',
        )

    def handle(self, *args, **options):
        if options['create_sample']:
            self.create_sample_logs()
        
        if options['cleanup_old']:
            self.cleanup_old_logs()

    def create_sample_logs(self):
        """Create sample admin logs for testing"""
        # Get admin users
        admin_users = User.objects.filter(is_staff=True)
        if not admin_users.exists():
            self.stdout.write(
                self.style.ERROR('No admin users found. Please create an admin user first.')
            )
            return

        # Sample IP addresses
        sample_ips = [
            '192.168.1.100', '192.168.1.101', '10.0.0.50', 
            '172.16.0.10', '203.112.218.5'
        ]

        actions = [
            ('CREATE', 'Student', 'Created new student registration'),
            ('UPDATE', 'Student', 'Updated student payment status'),
            ('DELETE', 'Student', 'Deleted duplicate student entry'),
            ('PAYMENT_VERIFY', 'Payment', 'Verified payment manually'),
            ('EMAIL_SENT', 'Student', 'Sent registration confirmation email'),
            ('RECEIPT_GENERATE', 'Receipt', 'Generated receipt for student'),
            ('LOGIN', '', 'Admin logged into dashboard'),
            ('LOGOUT', '', 'Admin logged out of dashboard'),
        ]

        # Create logs for the past 30 days
        logs_created = 0
        for i in range(50):  # Create 50 sample logs
            # Random timestamp in the past 30 days
            days_ago = random.randint(0, 30)
            hours_ago = random.randint(0, 23)
            timestamp = timezone.now() - timedelta(days=days_ago, hours=hours_ago)
            
            action, model_name, description = random.choice(actions)
            admin_user = random.choice(admin_users)
            ip_address = random.choice(sample_ips)
            
            # Create the log entry
            AdminLog.objects.create(
                admin_user=admin_user,
                action=action,
                model_name=model_name,
                object_id=str(random.randint(1, 100)) if model_name else '',
                description=description,
                ip_address=ip_address,
                timestamp=timestamp
            )
            logs_created += 1

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {logs_created} sample log entries.')
        )

    def cleanup_old_logs(self):
        """Clean up logs older than 90 days"""
        ninety_days_ago = timezone.now() - timedelta(days=90)
        old_logs = AdminLog.objects.filter(timestamp__lt=ninety_days_ago)
        count = old_logs.count()
        old_logs.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {count} old log entries.')
        )