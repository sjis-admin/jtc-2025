# registration/management/commands/send_pending_emails.py
from django.core.management.base import BaseCommand
from registration.models import Student, Receipt
from registration.views import send_registration_email

class Command(BaseCommand):
    help = 'Send confirmation emails to students who have paid but not received emails'
    
    def handle(self, *args, **options):
        # Get students who have paid but don't have email sent
        receipts = Receipt.objects.filter(
            student__is_paid=True,
            email_sent=False
        )
        
        sent_count = 0
        failed_count = 0
        
        for receipt in receipts:
            try:
                send_registration_email(receipt.student, receipt)
                sent_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Sent email to {receipt.student.name}')
                )
            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f'Failed to send email to {receipt.student.name}: {str(e)}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Email sending completed. Sent: {sent_count}, Failed: {failed_count}'
            )
        )
