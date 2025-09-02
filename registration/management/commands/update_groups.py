from django.core.management.base import BaseCommand
from registration.models import Student

class Command(BaseCommand):
    help = 'Update existing student groups based on new grade ranges'
    
    def handle(self, *args, **options):
        students = Student.objects.all()
        updated_count = 0
        
        for student in students:
            old_group = student.group
            grade_int = int(student.grade)
            
            # Apply new group logic
            if 3 <= grade_int <= 4:
                new_group = 'A'
            elif 5 <= grade_int <= 6:
                new_group = 'B'
            elif 7 <= grade_int <= 8:
                new_group = 'C'
            elif 9 <= grade_int <= 12:
                new_group = 'D'
            else:
                continue
            
            if old_group != new_group:
                student.group = new_group
                student.save()
                updated_count += 1
                self.stdout.write(
                    f'Updated {student.name} (Grade {student.grade}): '
                    f'{old_group} → {new_group}'
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {updated_count} student records'
            )
        )
