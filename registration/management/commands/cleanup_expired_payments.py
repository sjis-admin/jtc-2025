# Create this file: registration/management/commands/cleanup_expired_payments.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from registration.models import Payment
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up expired payments and mark them as expired'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without actually doing it',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Mark payments as expired that are older than this many days (default: 1)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days = options['days']
        
        cutoff_time = timezone.now() - timezone.timedelta(days=days)
        
        # Find expired payments
        expired_payments = Payment.objects.filter(
            status='PENDING',
            expires_at__lt=timezone.now()
        )
        
        # Also find payments that are older than specified days without expiry time
        old_pending_payments = Payment.objects.filter(
            status='PENDING',
            expires_at__isnull=True,
            created_at__lt=cutoff_time
        )
        
        total_expired = expired_payments.count()
        total_old_pending = old_pending_payments.count()
        total_count = total_expired + total_old_pending
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would mark {total_count} payments as expired:\n'
                    f'  - {total_expired} payments past their expiry time\n'
                    f'  - {total_old_pending} old pending payments (>{days} days)'
                )
            )
            
            if total_count > 0:
                self.stdout.write("Sample payments that would be affected:")
                for payment in list(expired_payments[:3]) + list(old_pending_payments[:3]):
                    self.stdout.write(
                        f"  - {payment.transaction_id} ({payment.student.name}) - "
                        f"Created: {payment.created_at}, Amount: ৳{payment.amount}"
                    )
        else:
            # Actually mark as expired
            updated_count = 0
            
            for payment in expired_payments:
                payment.status = 'EXPIRED'
                payment.save()
                updated_count += 1
                
            for payment in old_pending_payments:
                payment.status = 'EXPIRED'
                payment.expires_at = timezone.now()  # Set expiry time for tracking
                payment.save()
                updated_count += 1
            
            if updated_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully marked {updated_count} payments as expired'
                    )
                )
                logger.info(f'Cleaned up {updated_count} expired payments')
            else:
                self.stdout.write(
                    self.style.SUCCESS('No expired payments found')
                )
        
        return total_count