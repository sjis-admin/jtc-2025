# registration/management/commands/cleanup_incomplete_registrations.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from registration.models import Student, Payment

class Command(BaseCommand):
    help = 'Clean up incomplete registrations older than 24 hours'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Delete registrations older than this many hours (default: 24)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
    
    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        
        cutoff_time = timezone.now() - timedelta(hours=hours)
        
        # Find incomplete registrations
        incomplete_students = Student.objects.filter(
            is_paid=False,
            created_at__lt=cutoff_time
        )
        
        # Find failed payments
        failed_payments = Payment.objects.filter(
            status__in=['FAILED', 'CANCELLED'],
            created_at__lt=cutoff_time
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN - Would delete:')
            )
            self.stdout.write(f'- {incomplete_students.count()} incomplete student registrations')
            self.stdout.write(f'- {failed_payments.count()} failed payments')
        else:
            student_count = incomplete_students.count()
            payment_count = failed_payments.count()
            
            # Delete failed payments first (they have foreign key to students)
            failed_payments.delete()
            
            # Delete incomplete students
            incomplete_students.delete()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Cleaned up {student_count} incomplete registrations and {payment_count} failed payments'
                )
            )
