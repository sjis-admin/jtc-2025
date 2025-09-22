
# registration/management/commands/update_grade_orders.py
import re
from django.core.management.base import BaseCommand
from registration.models import Grade

class Command(BaseCommand):
    help = 'Inspects Grade names and updates the order field with the numeric value.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting to update grade orders...'))
        
        grades = Grade.objects.all()
        updated_count = 0
        
        for grade in grades:
            try:
                # Find the first number in the grade's name
                match = re.search(r'\d+', grade.name)
                
                if match:
                    numeric_value = int(match.group(0))
                    
                    # Check if the order needs updating
                    if grade.order != numeric_value:
                        self.stdout.write(f'Found grade: "{grade.name}". Current order: {grade.order}. Updating to: {numeric_value}')
                        grade.order = numeric_value
                        grade.save()
                        updated_count += 1
                    else:
                        self.stdout.write(f'Grade "{grade.name}" order is already correct ({grade.order}). Skipping.')
                else:
                    self.stdout.write(self.style.WARNING(f'Could not find a number in grade "{grade.name}". Skipping.'))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'An error occurred while processing grade "{grade.name}": {e}'))

        if updated_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated_count} grade orders.'))
        else:
            self.stdout.write(self.style.SUCCESS('All grade orders were already up to date. No changes made.'))

