from django.core.management.base import BaseCommand
from django.db.models import Q
from registration.models import Payment
from registration.utils import generate_secure_transaction_id

class Command(BaseCommand):
    help = 'Backfills empty transaction IDs for existing payments.'

    def handle(self, *args, **options):
        payments_to_update = Payment.objects.filter(Q(transaction_id__isnull=True) | Q(transaction_id=''))
        updated_count = 0
        for payment in payments_to_update:
            payment.transaction_id = generate_secure_transaction_id()
            payment.save()
            updated_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Successfully backfilled {updated_count} transaction IDs.'))
