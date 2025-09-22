# registration/management/commands/cleanup_duplicate_grades.py
from django.core.management.base import BaseCommand
from registration.models import Grade
from django.db.models import Count

class Command(BaseCommand):
    help = 'Deletes duplicate Grade objects based on name and order.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- Starting to clean up duplicate grades ---'))

        # Find duplicates based on 'order'
        duplicates = (
            Grade.objects.values('order')
            .annotate(order_count=Count('id'))
            .filter(order_count__gt=1)
        )

        deleted_count = 0
        for duplicate in duplicates:
            order = duplicate['order']
            self.stdout.write(f"Found duplicate entries for grade order: '{order}'")
            
            # Get all instances for this order, order by ID to keep the first one
            grades_to_check = Grade.objects.filter(order=order).order_by('id')
            grade_to_keep = grades_to_check.first()
            self.stdout.write(f"  Keeping grade with ID: {grade_to_keep.id} (Name: {grade_to_keep.name})")

            # Delete all other instances
            for grade_to_delete in grades_to_check[1:]:
                self.stdout.write(f"  Deleting duplicate grade with ID: {grade_to_delete.id} (Name: {grade_to_delete.name})")
                grade_to_delete.delete()
                deleted_count += 1

        if deleted_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted {deleted_count} duplicate grades.'))
        else:
            self.stdout.write(self.style.NOTICE('No duplicate grades found based on order.'))
